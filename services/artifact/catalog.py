from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from shared.contracts.artifact import (
    ArtifactPreview,
    ArtifactRecord,
    ArtifactStatus,
    CreateArtifactRequest,
)
from shared.db import get_engine


class ArtifactCatalog:
    def create(self, req: CreateArtifactRequest) -> ArtifactRecord:
        artifact_id = str(uuid.uuid4())
        engine = get_engine()

        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO artifacts (id, session_id, name, display_name, description,
                        type, status, schema_info, statistics, lineage, retention_class)
                    VALUES (:id, :session_id, :name, :display_name, :description,
                        :type, :status, :schema_info, :statistics, :lineage, :retention_class)
                """),
                {
                    "id": artifact_id,
                    "session_id": req.session_id,
                    "name": req.name,
                    "display_name": req.display_name,
                    "description": req.description,
                    "type": req.type.value,
                    "status": ArtifactStatus.READY.value,
                    "schema_info": req.schema_info.model_dump_json() if req.schema_info else None,
                    "statistics": req.statistics.model_dump_json() if req.statistics else None,
                    "lineage": req.lineage.model_dump_json() if req.lineage else None,
                    "retention_class": req.retention_class.value,
                },
            )
            conn.commit()

        return self.get(artifact_id)  # type: ignore

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        engine = get_engine()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM artifacts WHERE id = :id"),
                {"id": artifact_id},
            ).mappings().fetchone()

        if row is None:
            return None
        return self._row_to_record(row)

    def list_by_session(self, session_id: str) -> list[ArtifactRecord]:
        engine = get_engine()

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM artifacts WHERE session_id = :sid ORDER BY created_at"),
                {"sid": session_id},
            ).mappings().fetchall()

        return [self._row_to_record(r) for r in rows]

    def update_storage(
        self,
        artifact_id: str,
        storage_uri: str,
        size_bytes: int,
        preview: ArtifactPreview | None = None,
    ) -> None:
        engine = get_engine()

        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE artifacts
                    SET storage_uri = :uri,
                        size_bytes = :size,
                        extra_metadata = :extra_metadata,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "uri": storage_uri,
                    "size": size_bytes,
                    "extra_metadata": json.dumps(
                        {"preview": preview.model_dump()} if preview else {}
                    ),
                    "id": artifact_id,
                },
            )
            conn.commit()

    def _row_to_record(self, row) -> ArtifactRecord:
        schema_info = None
        if row["schema_info"]:
            raw = row["schema_info"]
            schema_info = json.loads(raw) if isinstance(raw, str) else raw

        statistics = None
        if row["statistics"]:
            raw = row["statistics"]
            statistics = json.loads(raw) if isinstance(raw, str) else raw

        lineage = None
        if row["lineage"]:
            raw = row["lineage"]
            lineage = json.loads(raw) if isinstance(raw, str) else raw

        preview = None
        extra_metadata = row.get("extra_metadata")
        if extra_metadata:
            raw = json.loads(extra_metadata) if isinstance(extra_metadata, str) else extra_metadata
            preview_data = raw.get("preview")
            if preview_data:
                preview = ArtifactPreview(**preview_data)

        return ArtifactRecord(
            id=str(row["id"]),
            session_id=row["session_id"],
            name=row["name"],
            display_name=row["display_name"],
            description=row["description"],
            type=row["type"],
            status=row["status"],
            storage_uri=row["storage_uri"],
            size_bytes=row["size_bytes"],
            schema_info=schema_info,
            statistics=statistics,
            preview=preview,
            lineage=lineage,
            retention_class=row["retention_class"],
            created_at=row["created_at"],
        )
