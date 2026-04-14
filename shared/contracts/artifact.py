from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    TABLE = "table"
    FILE = "file"
    CHART = "chart"
    REPORT = "report"
    TEXT = "text"


class ArtifactStatus(str, Enum):
    READY = "ready"
    PENDING = "pending"
    FAILED = "failed"


class RetentionClass(str, Enum):
    TEMPORARY = "temporary"
    REUSABLE = "reusable"
    PINNED = "pinned"
    PERSISTENT = "persistent"


class SchemaColumn(BaseModel):
    name: str
    logical_type: str
    nullable: bool = True


class TableSchema(BaseModel):
    columns: list[SchemaColumn]


class ArtifactStatistics(BaseModel):
    row_count: int | None = None
    column_count: int | None = None
    byte_size: int | None = None


class ArtifactLineage(BaseModel):
    source_kind: str  # "connected_source" | "derived" | "uploaded"
    parent_artifact_ids: list[str] = []
    transformation_summary: str | None = None
    connection_id: str | None = None
    query_text: str | None = None


class CreateArtifactRequest(BaseModel):
    session_id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    type: ArtifactType = ArtifactType.TABLE
    schema_info: TableSchema | None = None
    statistics: ArtifactStatistics | None = None
    lineage: ArtifactLineage | None = None
    retention_class: RetentionClass = RetentionClass.TEMPORARY


class ArtifactRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    type: ArtifactType = ArtifactType.TABLE
    status: ArtifactStatus = ArtifactStatus.READY
    storage_uri: str | None = None
    size_bytes: int | None = None
    schema_info: TableSchema | None = None
    statistics: ArtifactStatistics | None = None
    lineage: ArtifactLineage | None = None
    retention_class: RetentionClass = RetentionClass.TEMPORARY
    created_at: datetime = Field(default_factory=datetime.utcnow)
