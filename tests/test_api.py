from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.responses import Response as FastAPIResponse
from fastapi.testclient import TestClient

from simulation_service_dashboard.app import create_app
from simulation_service_dashboard.config import Settings


def make_settings(tmp_path: Path, backend_url: str = "http://simulation-service.test") -> Settings:
    return Settings(
        simulation_service_url=backend_url,
        polling_interval_seconds=0,
    )


def make_backend() -> FastAPI:
    backend = FastAPI()
    backend.state.jobs = []

    @backend.get("/api/v1/simulations")
    def list_jobs() -> list[dict[str, Any]]:
        return [dict(job) for job in backend.state.jobs]

    @backend.post("/api/v1/simulations", status_code=202)
    async def create_job(request: FastAPIRequest) -> dict[str, Any]:
        form = await request.form()
        backend.state.jobs.append(
            {
                "job_id": "842ee7cf-fb8a-4341-a1ed-9cf87aad83ab",
                "status": "RECEIVED",
                "system_status": "RUNNING",
                "profile_id": str(form["profile_id"]),
                "created_at": "2026-09-11T14:30:00Z",
                "updated_at": "2026-09-11T14:30:00Z",
            }
        )
        return {
            "job_id": "842ee7cf-fb8a-4341-a1ed-9cf87aad83ab",
            "status": "RECEIVED",
        }

    @backend.get("/api/v1/simulations/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "status": "SUCCEEDED",
            "system_status": "SUCCEEDED",
            "solver_status": "SUCCEEDED",
            "simulation_status": "PASS",
            "profile_id": "default",
            "remote_job_id": "remote-job",
            "result": {
                "ansys_result": {
                    "max_deformation": 0.1,
                    "max_stress": 500,
                    "final_relative_density": 0.97,
                    "density_distribution": {
                        "center_region_average": 0.98,
                        "edge_region_average": 0.96,
                        "minimum": 0.95,
                        "maximum": 0.99,
                    },
                },
                "geometry_diff": {"volume_difference_mm3": 1.2},
                "acceptance": {"passed": True, "checks": []},
                "process": {
                    "points": [
                        {
                            "time_hours": 0,
                            "temperature_celsius": 20,
                            "pressure_mpa": 0.1,
                        },
                        {
                            "time_hours": 2,
                            "temperature_celsius": 920,
                            "pressure_mpa": 100,
                        },
                    ],
                    "summary": {
                        "duration_hours": 2,
                        "peak_temperature_celsius": 920,
                        "peak_pressure_mpa": 100,
                    },
                },
                "artifacts": {
                    "model.inp": f"/api/v1/simulations/{job_id}/artifacts/model.inp",
                    "report.pdf": f"/api/v1/simulations/{job_id}/artifacts/report.pdf",
                },
            },
            "error": None,
            "created_at": "2026-09-11T14:30:00Z",
            "updated_at": "2026-09-11T14:35:00Z",
            "events": [
                {
                    "status": "SUCCEEDED",
                    "message": "Simulation completed",
                    "created_at": "2026-09-11T14:35:00Z",
                }
            ],
        }

    @backend.get("/api/v1/simulations/{job_id}/artifacts/{name}")
    def download_artifact(job_id: str, name: str) -> FastAPIResponse:
        if name == "http-audit.jsonl":
            return audit_content(job_id)
        return FastAPIResponse(content=f"artifact:{job_id}:{name}".encode())

    return backend


def audit_content(job_id: str) -> FastAPIResponse:
    return FastAPIResponse(
        status_code=200,
        content=(
            '{"sequence":1,"timestamp":"2026-09-11T14:30:05Z","job_id":"'
            + job_id
            + '","attempt":1,"request":{"method":"POST",'
            + '"url":"http://dev.htcmc.site/uploads/apdl","headers":{},'
            + '"files":[{"field":"file","filename":"model.inp",'
            + '"media_type":"application/octet-stream","size_bytes":7,'
            + '"sha256":"abc123","content_base64":"L1BSRVA3Cg=="}],'
            + '"content_json":null},"response":{"status_code":200,"headers":{},'
            + '"content_type":"application/json","content_json":{"path":"/tmp/model.inp"},'
            + '"content_base64":"e30="},"error":null}\n'
        ).encode(),
    )


def test_dashboard_page_serves_static_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(make_settings(tmp_path)))

    page = client.get("/")
    stylesheet = client.get("/assets/styles.css")
    script = client.get("/assets/app.js")

    assert page.status_code == 200
    assert 'href="/assets/styles.css"' in page.text
    assert 'src="/assets/app.js"' in page.text
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert '<script src="/assets/app.js" defer></script>' in page.text


def test_dashboard_lists_backend_simulations(tmp_path: Path) -> None:
    backend = make_backend()
    app = create_app(
        make_settings(tmp_path),
        transport=httpx.ASGITransport(backend),
    )
    client = TestClient(app)

    response = client.get("/api/simulations")

    assert response.status_code == 200
    assert response.json() == backend.state.jobs


def test_dashboard_uploads_step_files_and_polls_job(tmp_path: Path) -> None:
    backend = make_backend()
    app = create_app(
        make_settings(tmp_path),
        transport=httpx.ASGITransport(backend),
    )
    client = TestClient(app)

    response = client.post(
        "/api/simulations",
        data={"profile_id": "default"},
        files={
            "package_step": ("package.step", b"package step", "application/step"),
            "original_step": ("original.step", b"original step", "application/step"),
        },
    )
    poll = client.get("/api/simulations/842ee7cf-fb8a-4341-a1ed-9cf87aad83ab")
    detail = poll.json()

    assert response.status_code == 202
    assert response.json()["job_id"] == "842ee7cf-fb8a-4341-a1ed-9cf87aad83ab"
    assert poll.status_code == 200
    assert detail["result"]["process"]["summary"]["peak_temperature_celsius"] == 920
    assert detail["result"]["artifacts"]["model.inp"].startswith("/api/v1/simulations/")


def test_dashboard_proxies_artifact_download(tmp_path: Path) -> None:
    backend = make_backend()
    app = create_app(
        make_settings(tmp_path),
        transport=httpx.ASGITransport(backend),
    )
    client = TestClient(app)
    job_id = "842ee7cf-fb8a-4341-a1ed-9cf87aad83ab"

    response = client.get(f"/api/simulations/{job_id}/artifacts/model.inp")

    assert response.status_code == 200
    assert response.text == f"artifact:{job_id}:model.inp"
    assert response.headers["content-disposition"] == 'attachment; filename="model.inp"'


def test_dashboard_converts_http_audit_to_view_model(tmp_path: Path) -> None:
    backend = make_backend()

    app = create_app(
        make_settings(tmp_path),
        transport=httpx.ASGITransport(backend),
    )
    client = TestClient(app)
    job_id = "842ee7cf-fb8a-4341-a1ed-9cf87aad83ab"

    response = client.get(f"/api/simulations/{job_id}/http-audit")
    detail = client.get(f"/api/simulations/{job_id}/http-audit/1")

    assert response.status_code == 200
    assert response.json() == [
        {
            "sequence": 1,
            "timestamp": "2026-09-11T14:30:05Z",
            "attempt": 1,
            "method": "POST",
            "url": "http://dev.htcmc.site/uploads/apdl",
            "status_code": 200,
            "error": None,
            "request_summary": {
                "filename": "model.inp",
                "size_bytes": 7,
                "sha256": "abc123",
                "content_json": None,
            },
            "response_summary": {
                "content_type": "application/json",
                "content_json": {"path": "/tmp/model.inp"},
            },
        }
    ]
    assert detail.status_code == 200
    assert detail.json()["request"]["files"][0]["filename"] == "model.inp"
