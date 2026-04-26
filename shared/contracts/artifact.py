from __future__ import annotations

from typing import Any
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
    EVICTED = "evicted"


class ArtifactEvictionReason(str, Enum):
    EXPIRED_RETENTION = "expired_retention"
    QUOTA_PRESSURE = "quota_pressure"
    SESSION_EXPIRED = "session_expired"


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


class ArtifactPreview(BaseModel):
    sample_rows: list[dict[str, Any]]
    row_limit: int = 5


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
    is_pinned: bool = False
    expires_at: datetime | None = None


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
    preview: ArtifactPreview | None = None
    lineage: ArtifactLineage | None = None
    extra_metadata: dict[str, Any] | None = None
    retention_class: RetentionClass = RetentionClass.TEMPORARY
    is_pinned: bool = False
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ArtifactQuotaSummary(BaseModel):
    session_id: str
    quota_bytes: int
    used_bytes: int
    available_bytes: int
    over_quota: bool
    evictable_bytes: int


class EvictedArtifactInfo(BaseModel):
    artifact_id: str
    name: str
    reclaimed_bytes: int
    reason: ArtifactEvictionReason


class ArtifactEvictionCandidate(BaseModel):
    artifact_id: str
    session_id: str
    name: str
    retention_class: RetentionClass
    size_bytes: int
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    reason: ArtifactEvictionReason
    priority_rank: int


class ArtifactEvictionResult(BaseModel):
    session_id: str
    quota_bytes: int
    used_bytes_before: int
    used_bytes_after: int
    reclaimed_bytes: int
    evicted_artifacts: list[EvictedArtifactInfo]
