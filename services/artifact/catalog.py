from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from shared.contracts.artifact import (
    ArtifactEvictionCandidate,
    ArtifactEvictionReason,
    ArtifactEvictionResult,
    ArtifactPreview,
    ArtifactQuotaSummary,
    ArtifactRecord,
    ArtifactStatus,
    CreateArtifactRequest,
    EvictedArtifactInfo,
    RetentionClass,
)
from shared.db import get_engine


_RETENTION_TTLS: dict[RetentionClass, timedelta] = {
    RetentionClass.TEMPORARY: timedelta(days=7),
    RetentionClass.REUSABLE: timedelta(days=30),
}


class ArtifactCatalog:
    def create(self, req: CreateArtifactRequest) -> ArtifactRecord:
        artifact_id = str(uuid.uuid4())
        engine = get_engine()
        now = datetime.now(timezone.utc)
        is_pinned = req.is_pinned or req.retention_class == RetentionClass.PINNED
        expires_at = req.expires_at

        if expires_at is None and req.retention_class != RetentionClass.PINNED:
            expires_at = self._default_expiration(req.retention_class, now)

        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO artifacts (id, session_id, name, display_name, description,
                        type, status, schema_info, statistics, lineage, retention_class,
                        is_pinned, expires_at, last_accessed_at)
                    VALUES (:id, :session_id, :name, :display_name, :description,
                        :type, :status, :schema_info, :statistics, :lineage, :retention_class,
                        :is_pinned, :expires_at, :last_accessed_at)
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
                    "is_pinned": is_pinned,
                    "expires_at": expires_at,
                    "last_accessed_at": now,
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

    def list_by_session(self, session_id: str, include_evicted: bool = False) -> list[ArtifactRecord]:
        engine = get_engine()
        query = "SELECT * FROM artifacts WHERE session_id = :sid"
        if not include_evicted:
            query += " AND status != 'evicted'"
        query += " ORDER BY created_at"

        with engine.connect() as conn:
            rows = conn.execute(
                text(query),
                {"sid": session_id},
            ).mappings().fetchall()

        return [self._row_to_record(r) for r in rows]

    def list_eviction_candidates(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[ArtifactEvictionCandidate]:
        engine = get_engine()
        as_of = datetime.now(timezone.utc)
        params: dict[str, object] = {
            "as_of": as_of,
            "limit": limit,
        }
        where_clauses = [
            "status != 'evicted'",
            "storage_uri IS NOT NULL",
            "is_pinned = FALSE",
            "retention_class NOT IN ('persistent', 'pinned')",
        ]

        if session_id is not None:
            where_clauses.append("session_id = :session_id")
            params["session_id"] = session_id

        query = f"""
            SELECT * FROM artifacts
            WHERE {' AND '.join(where_clauses)}
            ORDER BY
                CASE
                    WHEN expires_at IS NOT NULL AND expires_at <= :as_of THEN 0
                    ELSE 1
                END,
                CASE retention_class
                    WHEN 'temporary' THEN 0
                    WHEN 'reusable' THEN 1
                    ELSE 2
                END,
                COALESCE(last_accessed_at, created_at),
                created_at
            LIMIT :limit
        """

        with engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().fetchall()

        candidates: list[ArtifactEvictionCandidate] = []
        for index, row in enumerate(rows, start=1):
            reason = self._eviction_reason_for_row(row, as_of)
            if reason is None:
                continue
            candidates.append(
                ArtifactEvictionCandidate(
                    artifact_id=str(row["id"]),
                    session_id=row["session_id"],
                    name=row["name"],
                    retention_class=row["retention_class"],
                    size_bytes=row["size_bytes"] or 0,
                    expires_at=row.get("expires_at"),
                    last_accessed_at=row.get("last_accessed_at"),
                    reason=reason,
                    priority_rank=index,
                )
            )
        return candidates

    def get_quota_summary(self, session_id: str, quota_bytes: int) -> ArtifactQuotaSummary:
        used_bytes = self._sum_bytes_for_query(
            "session_id = :session_id AND status != 'evicted' AND storage_uri IS NOT NULL",
            {"session_id": session_id},
        )
        evictable_bytes = self._sum_bytes_for_query(
            """
            session_id = :session_id
            AND status != 'evicted'
            AND storage_uri IS NOT NULL
            AND is_pinned = FALSE
            AND retention_class NOT IN ('persistent', 'pinned')
            """,
            {"session_id": session_id},
        )

        available_bytes = max(quota_bytes - used_bytes, 0)
        return ArtifactQuotaSummary(
            session_id=session_id,
            quota_bytes=quota_bytes,
            used_bytes=used_bytes,
            available_bytes=available_bytes,
            over_quota=used_bytes > quota_bytes,
            evictable_bytes=evictable_bytes,
        )

    def list_session_cleanup_candidates(self, session_id: str) -> list[ArtifactRecord]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT * FROM artifacts
                    WHERE session_id = :session_id
                      AND status != 'evicted'
                      AND storage_uri IS NOT NULL
                      AND is_pinned = FALSE
                      AND retention_class NOT IN ('persistent', 'pinned')
                    ORDER BY
                        CASE retention_class
                            WHEN 'temporary' THEN 0
                            WHEN 'reusable' THEN 1
                            ELSE 2
                        END,
                        COALESCE(last_accessed_at, created_at),
                        created_at
                """),
                {"session_id": session_id},
            ).mappings().fetchall()

        return [self._row_to_record(row) for row in rows]

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

    def touch_access(self, artifact_id: str) -> None:
        engine = get_engine()

        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE artifacts
                    SET last_accessed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": artifact_id},
            )
            conn.commit()

    def set_pinned(self, artifact_id: str, is_pinned: bool) -> ArtifactRecord | None:
        engine = get_engine()
        now = datetime.now(timezone.utc)

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT retention_class FROM artifacts WHERE id = :id"),
                {"id": artifact_id},
            ).mappings().fetchone()
            if row is None:
                return None

            retention_class = RetentionClass(row["retention_class"])
            expires_at = None if is_pinned else self._default_expiration(retention_class, now)

            conn.execute(
                text("""
                    UPDATE artifacts
                    SET is_pinned = :is_pinned,
                        expires_at = :expires_at,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": artifact_id,
                    "is_pinned": is_pinned,
                    "expires_at": expires_at,
                },
            )
            conn.commit()

        return self.get(artifact_id)

    def mark_evicted(
        self,
        artifact_id: str,
        reason: ArtifactEvictionReason,
    ) -> EvictedArtifactInfo | None:
        engine = get_engine()
        evicted_at = datetime.now(timezone.utc).isoformat()

        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id, name, size_bytes, extra_metadata
                    FROM artifacts
                    WHERE id = :id
                """),
                {"id": artifact_id},
            ).mappings().fetchone()
            if row is None:
                return None

            extra_metadata = row["extra_metadata"] or {}
            if isinstance(extra_metadata, str):
                extra_metadata = json.loads(extra_metadata)

            reclaimed_bytes = row["size_bytes"] or 0
            extra_metadata["eviction"] = {
                "reason": reason.value,
                "evicted_at": evicted_at,
                "reclaimed_bytes": reclaimed_bytes,
            }

            conn.execute(
                text("""
                    UPDATE artifacts
                    SET status = :status,
                        storage_uri = NULL,
                        size_bytes = 0,
                        updated_at = NOW(),
                        extra_metadata = :extra_metadata
                    WHERE id = :id
                """),
                {
                    "id": artifact_id,
                    "status": ArtifactStatus.EVICTED.value,
                    "extra_metadata": json.dumps(extra_metadata),
                },
            )
            conn.commit()

        return EvictedArtifactInfo(
            artifact_id=str(row["id"]),
            name=row["name"],
            reclaimed_bytes=reclaimed_bytes,
            reason=reason,
        )

    def build_eviction_result(
        self,
        session_id: str,
        quota_bytes: int,
        used_bytes_before: int,
        evicted_artifacts: list[EvictedArtifactInfo],
    ) -> ArtifactEvictionResult:
        used_bytes_after = self.get_quota_summary(session_id, quota_bytes).used_bytes
        reclaimed_bytes = sum(item.reclaimed_bytes for item in evicted_artifacts)
        return ArtifactEvictionResult(
            session_id=session_id,
            quota_bytes=quota_bytes,
            used_bytes_before=used_bytes_before,
            used_bytes_after=used_bytes_after,
            reclaimed_bytes=reclaimed_bytes,
            evicted_artifacts=evicted_artifacts,
        )

    def _default_expiration(
        self,
        retention_class: RetentionClass,
        now: datetime,
    ) -> datetime | None:
        ttl = _RETENTION_TTLS.get(retention_class)
        if ttl is None:
            return None
        return now + ttl

    def _sum_bytes_for_query(self, where_clause: str, params: dict[str, object]) -> int:
        engine = get_engine()
        query = f"SELECT COALESCE(SUM(size_bytes), 0) AS total_bytes FROM artifacts WHERE {where_clause}"
        with engine.connect() as conn:
            row = conn.execute(text(query), params).mappings().fetchone()
        return int(row["total_bytes"] if row else 0)

    def _eviction_reason_for_row(
        self,
        row,
        as_of: datetime,
    ) -> ArtifactEvictionReason | None:
        expires_at = row.get("expires_at")
        if expires_at is not None and expires_at <= as_of:
            return ArtifactEvictionReason.EXPIRED_RETENTION
        return ArtifactEvictionReason.QUOTA_PRESSURE

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
        extra_metadata = None
        raw_metadata = row.get("extra_metadata")
        if raw_metadata:
            extra_metadata = (
                json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
            )
            preview_data = extra_metadata.get("preview")
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
            extra_metadata=extra_metadata,
            retention_class=row["retention_class"],
            is_pinned=row.get("is_pinned", False),
            expires_at=row.get("expires_at"),
            last_accessed_at=row.get("last_accessed_at"),
            created_at=row["created_at"],
        )
