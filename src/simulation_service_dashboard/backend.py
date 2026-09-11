import json
from typing import Any

import httpx


class BackendUnavailable(Exception):
    pass


class SimulationServiceBackend:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def list_jobs(self) -> list[dict[str, Any]]:
        jobs = await self._get_json("/api/v1/simulations")
        return jobs if isinstance(jobs, list) else []

    async def create_job(
        self,
        *,
        files: dict[str, tuple[str, bytes, str]],
        data: dict[str, str],
    ) -> dict[str, Any]:
        job = await self._request_json(
            "POST",
            "/api/v1/simulations",
            data=data,
            files=files,
        )
        return job if isinstance(job, dict) else {}

    async def get_job(self, job_id: str) -> dict[str, Any]:
        job = await self._get_json(f"/api/v1/simulations/{job_id}")
        return job if isinstance(job, dict) else {}

    async def download_artifact(self, job_id: str, name: str) -> httpx.Response:
        return await self._request(
            "GET",
            f"/api/v1/simulations/{job_id}/artifacts/{name}",
        )

    async def http_audit(self, job_id: str) -> list[dict[str, Any]]:
        response = await self.download_artifact(job_id, "http-audit.jsonl")
        try:
            return [json.loads(line) for line in response.text.splitlines() if line]
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BackendUnavailable("Invalid HTTP audit from simulation service") from error

    async def _get_json(self, path: str) -> Any:
        return (await self._request("GET", path)).json()

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        return (await self._request(method, path, **kwargs)).json()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise BackendUnavailable("Cannot reach simulation service") from error
        if response.status_code >= 500:
            raise BackendUnavailable("Simulation service returned a server error")
        return response


class AnsysServiceBackend:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def _request(self, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.client.get(path, **kwargs)
        except httpx.HTTPError as error:
            raise BackendUnavailable("Cannot reach ansys-hip-service") from error
        if response.status_code >= 500:
            raise BackendUnavailable("ansys-hip-service returned a server error")
        return response

    async def _json(self, path: str) -> Any:
        return (await self._request(path)).json()

    async def health(self) -> dict[str, Any]:
        health = await self._json("/health")
        return health if isinstance(health, dict) else {}

    async def list_jobs(self) -> list[dict[str, Any]]:
        jobs = await self._json("/jobs")
        return jobs if isinstance(jobs, list) else []

    async def job_log(self, job_id: str, source: str = "job.log") -> httpx.Response:
        return await self._request(f"/jobs/{job_id}/log", params={"source": source})

    async def service_log(self) -> httpx.Response:
        return await self._request("/service/log")

    async def artifacts(self, job_id: str) -> list[str]:
        names = await self._json(f"/jobs/{job_id}/artifacts")
        return names if isinstance(names, list) else []

    async def artifact(self, job_id: str, name: str) -> httpx.Response:
        return await self._request(f"/jobs/{job_id}/artifacts/{name}")
