from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SimulationJobSummary(BaseModel):
    job_id: str
    status: str
    system_status: str
    profile_id: str
    created_at: datetime
    updated_at: datetime


class CreateSimulationResponse(BaseModel):
    job_id: str
    status: str


class AuditRequestSummary(BaseModel):
    filename: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    content_json: Any | None = None


class AuditResponseSummary(BaseModel):
    content_type: str | None = None
    content_json: Any | None = None


class HttpAuditSummary(BaseModel):
    sequence: int
    timestamp: datetime
    attempt: int
    method: str
    url: str
    status_code: int | None = None
    error: dict[str, str] | None = None
    request_summary: AuditRequestSummary
    response_summary: AuditResponseSummary | None = None
