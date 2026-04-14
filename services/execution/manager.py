from __future__ import annotations

import io
import logging

import httpx
import pyarrow.parquet as pq

from sqlalchemy import text

from shared.contracts.artifact import (
    ArtifactLineage,
    ArtifactStatistics,
    CreateArtifactRequest,
    ArtifactRecord,
    SchemaColumn,
    TableSchema,
)
from shared.contracts.connection import ConnectionConfig, ConnectionRecord
from shared.contracts.execution import ExecutionRequest, ExecutionResult
from shared.db import get_engine
from shared.settings import settings

logger = logging.getLogger(__name__)


class ExecutionManager:
    # --- Connection registry (embedded for Phase 1) ---

    def list_connections(self) -> list[ConnectionRecord]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM connections WHERE status = 'active' ORDER BY name")
            ).mappings().fetchall()
        return [self._row_to_connection(r) for r in rows]

    def get_connection_by_id(self, connection_id: str) -> ConnectionRecord | None:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM connections WHERE id = :id"),
                {"id": connection_id},
            ).mappings().fetchone()
        return self._row_to_connection(row) if row else None

    def get_connection_by_name(self, name: str) -> ConnectionRecord | None:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM connections WHERE name = :name"),
                {"name": name},
            ).mappings().fetchone()
        return self._row_to_connection(row) if row else None

    # --- Execution ---

    async def execute(self, req: ExecutionRequest) -> ExecutionResult:
        # 1. Resolve connection
        connection = self._resolve_connection(req)
        if connection is None:
            return ExecutionResult(
                execution_id=req.id,
                status="error",
                error_message="Connection not found",
            )

        # 2. Call the SQL runtime
        try:
            parquet_bytes, row_count, columns = await self._call_sql_runtime(
                connection=connection,
                query=req.tool.payload.get("query", ""),
            )
        except Exception as e:
            logger.error("Runtime execution failed: %s", e)
            return ExecutionResult(
                execution_id=req.id,
                status="error",
                error_message=str(e),
            )

        # 3. Extract schema from Parquet
        schema_info = self._extract_schema(parquet_bytes)

        # 4. Determine artifact name
        artifact_name = "query_result"
        if req.expected_outputs:
            artifact_name = req.expected_outputs[0].name

        # 5. Register artifact via Artifact Service
        try:
            artifact = await self._register_artifact(
                session_id=req.session_id,
                name=artifact_name,
                parquet_bytes=parquet_bytes,
                schema_info=schema_info,
                row_count=row_count,
                connection=connection,
                query=req.tool.payload.get("query", ""),
            )
        except Exception as e:
            logger.error("Artifact registration failed: %s", e)
            return ExecutionResult(
                execution_id=req.id,
                status="error",
                error_message=f"Failed to store artifact: {e}",
            )

        return ExecutionResult(
            execution_id=req.id,
            status="success",
            artifact_ids=[artifact.id],
        )

    # --- Internal helpers ---

    def _resolve_connection(self, req: ExecutionRequest) -> ConnectionRecord | None:
        if req.target and req.target.connection_id:
            return self.get_connection_by_id(req.target.connection_id)
        if req.target and req.target.connection_name:
            return self.get_connection_by_name(req.target.connection_name)
        return None

    async def _call_sql_runtime(
        self, connection: ConnectionRecord, query: str
    ) -> tuple[bytes, int, list[str]]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.sql_runtime_url}/execute",
                json={
                    "connection_type": connection.type,
                    "connection_config": connection.config.model_dump(),
                    "query": query,
                },
            )
            resp.raise_for_status()

        row_count = int(resp.headers.get("X-Row-Count", "0"))
        columns = resp.headers.get("X-Columns", "").split(",")
        return resp.content, row_count, columns

    def _extract_schema(self, parquet_bytes: bytes) -> TableSchema:
        buf = io.BytesIO(parquet_bytes)
        pf = pq.ParquetFile(buf)
        arrow_schema = pf.schema_arrow

        columns = []
        for field in arrow_schema:
            columns.append(
                SchemaColumn(
                    name=field.name,
                    logical_type=str(field.type),
                    nullable=field.nullable,
                )
            )
        return TableSchema(columns=columns)

    async def _register_artifact(
        self,
        session_id: str,
        name: str,
        parquet_bytes: bytes,
        schema_info: TableSchema,
        row_count: int,
        connection: ConnectionRecord,
        query: str,
    ) -> ArtifactRecord:
        create_req = CreateArtifactRequest(
            session_id=session_id,
            name=name,
            schema_info=schema_info,
            statistics=ArtifactStatistics(
                row_count=row_count,
                column_count=len(schema_info.columns),
                byte_size=len(parquet_bytes),
            ),
            lineage=ArtifactLineage(
                source_kind="connected_source",
                connection_id=connection.id,
                query_text=query,
            ),
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Register metadata
            resp = await client.post(
                f"{settings.artifact_service_url}/artifacts",
                json=create_req.model_dump(),
            )
            resp.raise_for_status()
            artifact = ArtifactRecord(**resp.json())

            # Upload payload
            resp = await client.put(
                f"{settings.artifact_service_url}/artifacts/{artifact.id}/upload",
                content=parquet_bytes,
                headers={"Content-Type": "application/octet-stream"},
            )
            resp.raise_for_status()

        return artifact

    def _row_to_connection(self, row) -> ConnectionRecord:
        import json

        config_raw = row["config"]
        config_dict = json.loads(config_raw) if isinstance(config_raw, str) else config_raw

        return ConnectionRecord(
            id=str(row["id"]),
            name=row["name"],
            display_name=row["display_name"],
            type=row["type"],
            status=row["status"],
            config=ConnectionConfig(**config_dict),
            created_at=row["created_at"],
        )
