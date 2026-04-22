from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    user_id: str | None = None
    status: JobStatus = JobStatus.SUBMITTED
    execution_request: dict = {}
    result: dict | None = None
    logs: list[str] = []
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
