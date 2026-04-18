from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RuntimeRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    display_name: str | None = None
    type: str  # "sql" | "python" | ...
    endpoint_url: str
    status: str = "active"
    capabilities: list[str] = []
    created_at: datetime | None = None
