from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response
from fastapi.testclient import TestClient

from simulation_service_dashboard.app import create_app


def make_ansys_backend() -> FastAPI:
    backend = FastAPI()
    backend.state.jobs = [
        {
            "id": "ansys-job",
            "method": "passthrough",
            "status": "succeeded",
            "fidelity": "passthrough",
            "created_at": "2026-09-11T15:30:00Z",
            "started_at": "2026-09-11T15:30:01Z",
            "finished_at": "2026-09-11T15:30:10Z",
            "error": None,
            "log_url": "/jobs/ansys-job/log",
            "result_url": "/jobs/ansys-job/result",
            "artifacts_url": "/jobs/ansys-job/artifacts",
            "stages": None,
        }
    ]

    @backend.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mapdl_found": True,
            "license_env_set": True,
            "queue_running": 1,
            "queue_pending": 2,
            "passthrough_enabled": True,
            "version": "0.1.0",
        }

    @backend.get("/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [dict(job) for job in backend.state.jobs]

    @backend.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = dict(backend.state.jobs[0])
        job["id"] = job_id
        return job

    @backend.get("/jobs/{job_id}/log")
    def job_log(job_id: str) -> PlainTextResponse:
        return PlainTextResponse(f"job log for {job_id}\n")

    @backend.get("/service/log")
    def service_log() -> PlainTextResponse:
        return PlainTextResponse("service log\n")

    @backend.get("/jobs/{job_id}/artifacts")
    def artifacts(job_id: str) -> list[str]:
        return ["deform.csv", "job.out"]

    @backend.get("/jobs/{job_id}/artifacts/{name}")
    def artifact(job_id: str, name: str) -> Response:
        return Response(content=f"{job_id}:{name}".encode())

    return backend


def make_dashboard_client(ansys_backend: FastAPI) -> TestClient:
    app = create_app(
        transport=httpx.ASGITransport(app=ansys_backend),
    )
    return TestClient(app)


def test_dashboard_exposes_ansys_health() -> None:
    client = make_dashboard_client(make_ansys_backend())

    response = client.get("/api/ansys/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["passthrough_enabled"] is True


def test_dashboard_lists_ansys_jobs() -> None:
    client = make_dashboard_client(make_ansys_backend())

    response = client.get("/api/ansys/jobs")

    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == ["ansys-job"]


def test_dashboard_proxies_ansys_logs() -> None:
    client = make_dashboard_client(make_ansys_backend())

    job_log = client.get("/api/ansys/jobs/ansys-job/log")
    service_log = client.get("/api/ansys/service-log")

    assert job_log.status_code == 200
    assert job_log.text == "job log for ansys-job\n"
    assert service_log.status_code == 200
    assert service_log.text == "service log\n"


def test_dashboard_lists_and_downloads_ansys_artifacts() -> None:
    client = make_dashboard_client(make_ansys_backend())

    artifacts = client.get("/api/ansys/jobs/ansys-job/artifacts")
    artifact = client.get("/api/ansys/jobs/ansys-job/artifacts/deform.csv")

    assert artifacts.status_code == 200
    assert artifacts.json() == ["deform.csv", "job.out"]
    assert artifact.status_code == 200
    assert artifact.text == "ansys-job:deform.csv"
    assert artifact.headers["content-disposition"] == 'attachment; filename="deform.csv"'
