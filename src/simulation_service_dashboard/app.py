from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from simulation_service_dashboard.backend import (
    AnsysServiceBackend,
    BackendUnavailable,
    SimulationServiceBackend,
)
from simulation_service_dashboard.config import Settings
from simulation_service_dashboard.schemas import (
    CreateSimulationResponse,
    HttpAuditSummary,
    SimulationJobSummary,
)

STATIC_DIR = Path(__file__).parent / "static"


def get_backend(request: Request) -> SimulationServiceBackend:
    backend = request.app.state.backend
    if not isinstance(backend, SimulationServiceBackend):
        raise RuntimeError("Backend is not initialized")
    return backend


def get_ansys_backend(request: Request) -> AnsysServiceBackend:
    backend = request.app.state.ansys_backend
    if not isinstance(backend, AnsysServiceBackend):
        raise RuntimeError("Ansys backend is not initialized")
    return backend


Backend = Annotated[SimulationServiceBackend, Depends(get_backend)]
AnsysBackend = Annotated[AnsysServiceBackend, Depends(get_ansys_backend)]


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    http_client = httpx.AsyncClient(
        base_url=resolved_settings.simulation_service_url,
        transport=transport,
        timeout=resolved_settings.request_timeout_seconds,
        follow_redirects=True,
    )
    ansys_http_client = httpx.AsyncClient(
        base_url=resolved_settings.ansys_service_url,
        transport=transport,
        timeout=resolved_settings.request_timeout_seconds,
        follow_redirects=True,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await http_client.aclose()
        await ansys_http_client.aclose()

    app = FastAPI(
        title="Simulation Service Dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.backend = SimulationServiceBackend(http_client)
    app.state.ansys_backend = AnsysServiceBackend(ansys_http_client)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/api/simulations", response_model=list[SimulationJobSummary])
    async def list_simulations(backend: Backend) -> list[dict[str, Any]]:
        try:
            return await backend.list_jobs()
        except BackendUnavailable as error:
            raise _backend_error(error) from error

    @app.post(
        "/api/simulations",
        status_code=202,
        response_model=CreateSimulationResponse,
    )
    async def create_simulation(
        backend: Backend,
        package_step: UploadFile = File(...),
        original_step: UploadFile = File(...),
        profile_id: Annotated[str, Form()] = "default",
    ) -> dict[str, Any]:
        package_content = await package_step.read()
        original_content = await original_step.read()
        try:
            response = await backend.create_job(
                files={
                    "package_step": (
                        package_step.filename or "package.step",
                        package_content,
                        package_step.content_type or "application/step",
                    ),
                    "original_step": (
                        original_step.filename or "original.step",
                        original_content,
                        original_step.content_type or "application/step",
                    ),
                },
                data={"profile_id": profile_id},
            )
        except BackendUnavailable as error:
            raise _backend_error(error) from error
        if "job_id" not in response or "status" not in response:
            raise _upstream_error(response)
        return response

    @app.get("/api/simulations/{job_id}")
    async def get_simulation(backend: Backend, job_id: str) -> Any:
        try:
            return await backend.get_job(job_id)
        except BackendUnavailable as error:
            raise _backend_error(error) from error

    @app.get("/api/simulations/{job_id}/artifacts/{artifact_name}")
    async def download_artifact(
        backend: Backend,
        job_id: str,
        artifact_name: str,
    ) -> Response:
        try:
            upstream = await backend.download_artifact(job_id, artifact_name)
        except BackendUnavailable as error:
            raise _backend_error(error) from error
        if upstream.status_code == 404:
            raise HTTPException(status_code=404, detail="Artifact is not ready")
        if upstream.is_error:
            raise _upstream_error({"detail": upstream.text})
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{artifact_name}"',
            },
        )

    @app.get("/api/simulations/{job_id}/http-audit", response_model=list[HttpAuditSummary])
    async def get_http_audit(backend: Backend, job_id: str) -> list[dict[str, Any]]:
        try:
            records = await backend.http_audit(job_id)
        except BackendUnavailable as error:
            raise _backend_error(error) from error
        return [_render_audit_summary(record) for record in records]

    @app.get("/api/simulations/{job_id}/http-audit/{sequence}")
    async def get_http_audit_exchange(
        backend: Backend,
        job_id: str,
        sequence: int,
    ) -> Any:
        try:
            records = await backend.http_audit(job_id)
        except BackendUnavailable as error:
            raise _backend_error(error) from error
        for record in records:
            if record.get("sequence") == sequence:
                return record
        raise HTTPException(status_code=404, detail="HTTP audit exchange not found")

    @app.get("/api/ansys/health")
    async def ansys_health(ansys_backend: AnsysBackend) -> Any:
        try:
            return await ansys_backend.health()
        except BackendUnavailable as error:
            raise _backend_error(error) from error

    @app.get("/api/ansys/jobs")
    async def ansys_jobs(ansys_backend: AnsysBackend) -> list[dict[str, Any]]:
        try:
            return await ansys_backend.list_jobs()
        except BackendUnavailable as error:
            raise _backend_error(error) from error

    @app.get("/api/ansys/jobs/{job_id}/log")
    async def ansys_job_log(
        ansys_backend: AnsysBackend,
        job_id: str,
        source: str = "job.log",
    ) -> Response:
        try:
            upstream = await ansys_backend.job_log(job_id, source)
        except BackendUnavailable as error:
            raise _backend_error(error) from error
        return _text_response(upstream)

    @app.get("/api/ansys/service-log")
    async def ansys_service_log(ansys_backend: AnsysBackend) -> Response:
        try:
            upstream = await ansys_backend.service_log()
        except BackendUnavailable as error:
            raise _backend_error(error) from error
        return _text_response(upstream)

    @app.get("/api/ansys/jobs/{job_id}/artifacts")
    async def ansys_artifacts(
        ansys_backend: AnsysBackend,
        job_id: str,
    ) -> list[str]:
        try:
            return await ansys_backend.artifacts(job_id)
        except BackendUnavailable as error:
            raise _backend_error(error) from error

    @app.get("/api/ansys/jobs/{job_id}/artifacts/{artifact_name}")
    async def ansys_artifact(
        ansys_backend: AnsysBackend,
        job_id: str,
        artifact_name: str,
    ) -> Response:
        try:
            upstream = await ansys_backend.artifact(job_id, artifact_name)
        except BackendUnavailable as error:
            raise _backend_error(error) from error
        if upstream.is_error:
            raise _upstream_error({"detail": upstream.text})
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers={"Content-Disposition": f'attachment; filename="{artifact_name}"'},
        )

    return app


def _render_audit_summary(record: dict[str, Any]) -> dict[str, Any]:
    request = record.get("request", {})
    files = request.get("files", [])
    primary_file = files[0] if files else {}
    response = record.get("response")
    return {
        "sequence": record["sequence"],
        "timestamp": record["timestamp"],
        "attempt": record.get("attempt", 1),
        "method": request.get("method", ""),
        "url": request.get("url", ""),
        "status_code": response.get("status_code") if response is not None else None,
        "error": record.get("error"),
        "request_summary": {
            "filename": primary_file.get("filename"),
            "size_bytes": primary_file.get("size_bytes"),
            "sha256": primary_file.get("sha256"),
            "content_json": request.get("content_json"),
        },
        "response_summary": (
            {
                "content_type": response.get("content_type"),
                "content_json": response.get("content_json"),
            }
            if response is not None
            else None
        ),
    }


def _backend_error(error: BackendUnavailable) -> HTTPException:
    return HTTPException(status_code=503, detail=str(error))


def _upstream_error(detail: Any) -> HTTPException:
    return HTTPException(status_code=502, detail={"upstream": detail})


def _text_response(upstream: httpx.Response) -> Response:
    if upstream.is_error:
        raise _upstream_error({"detail": upstream.text})
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "text/plain"),
    )
