from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConnectionConfig(BaseModel):
    host: str | None = None
    port: int | None = None
    database: str | None = None
    path: str | None = None  # for SQLite
    schema_name: str | None = None
    options: dict = {}


class ConnectionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    display_name: str | None = None
    type: str  # "sqlite" | "postgresql" | ...
    status: str = "active"
    config: ConnectionConfig = ConnectionConfig()
    created_at: datetime | None = None
