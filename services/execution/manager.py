from __future__ import annotations

import base64
import io
import json
import logging
import os

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
from shared.contracts.runtime import RuntimeRecord
from shared.contracts.skill import (
    SkillRecord,
    SkillScope,
    SkillTrigger,
    SkillInstructions,
)
from shared.contracts.policy import (
    PolicyRecord,
    PolicyScope as PolicyScopeModel,
    PolicyCondition,
    PolicyEffect,
    PolicyEvaluation,
)
from shared.contracts.topic import (
    TopicProfile,
    UserTopicAssignment,
    ResolvedTopicContext,
)
from shared.db import get_engine
from shared.settings import settings

logger = logging.getLogger(__name__)

# Mapping from tool names to runtime types
TOOL_RUNTIME_MAP = {
    "query_sql": "sql",
    "python_transform": "python",
}


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

    # --- Skill registry ---

    def list_skills(self) -> list[SkillRecord]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM skills WHERE status = 'active' ORDER BY name")
            ).mappings().fetchall()
        return [self._row_to_skill(r) for r in rows]

    def get_skills_for_context(
        self,
        connection_names: list[str] | None = None,
        user_message: str | None = None,
    ) -> list[SkillRecord]:
        """Return skills whose scope/triggers match the current context."""
        all_skills = self.list_skills()
        matched: list[SkillRecord] = []

        for skill in all_skills:
            # Global skills always match
            if skill.scope.level == "global":
                matched.append(skill)
                continue

            # Connection-scoped: match if any connection name is referenced
            if skill.scope.connection_names and connection_names:
                if set(skill.scope.connection_names) & set(connection_names):
                    matched.append(skill)
                    continue

            # Trigger-based matching (keyword in user message)
            if user_message and skill.triggers:
                msg_lower = user_message.lower()
                for trigger in skill.triggers:
                    if trigger.kind == "keyword" and trigger.value.lower() in msg_lower:
                        matched.append(skill)
                        break

        return matched

    # --- Policy registry ---

    def list_policies(self) -> list[PolicyRecord]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM policies WHERE status = 'active' ORDER BY priority DESC, name")
            ).mappings().fetchall()
        return [self._row_to_policy(r) for r in rows]

    def get_policies_for_context(
        self,
        tool_name: str | None = None,
        connection_type: str | None = None,
        topic_profile_ids: list[str] | None = None,
    ) -> list[PolicyRecord]:
        """Return policies matching the execution context, ordered by priority."""
        all_policies = self.list_policies()
        matched: list[PolicyRecord] = []

        for policy in all_policies:
            # Global scope always matches
            if policy.scope.level == "global":
                matched.append(policy)
                continue

            # Topic-scoped: match if policy is bound to one of the active topic profiles
            if policy.scope.topic_profile_ids and topic_profile_ids:
                if set(policy.scope.topic_profile_ids) & set(topic_profile_ids):
                    matched.append(policy)
                    continue

            # Connection-scoped: match if source type is in condition
            if connection_type and policy.condition.source_types:
                if connection_type in policy.condition.source_types:
                    matched.append(policy)
                    continue

            # Tool-scoped: match if tool name is in condition
            if tool_name and policy.condition.tool_names:
                if tool_name in policy.condition.tool_names:
                    matched.append(policy)
                    continue

        return matched

    def evaluate_policies(
        self,
        tool_name: str | None = None,
        connection_type: str | None = None,
        topic_profile_ids: list[str] | None = None,
        estimated_row_count: int | None = None,
    ) -> PolicyEvaluation:
        """Evaluate all matching policies and merge their effects."""
        policies = self.get_policies_for_context(
            tool_name=tool_name,
            connection_type=connection_type,
            topic_profile_ids=topic_profile_ids,
        )

        evaluation = PolicyEvaluation()
        evaluation.matched_policies = policies

        for policy in policies:
            # Check row count threshold condition
            if (
                policy.condition.estimated_row_count_above is not None
                and estimated_row_count is not None
                and estimated_row_count <= policy.condition.estimated_row_count_above
            ):
                # Condition not met — skip this policy's effects
                continue

            effect = policy.effect

            if effect.denied_tool_names:
                evaluation.denied_tools.extend(effect.denied_tool_names)
            if effect.required_tool_names:
                evaluation.required_tools.extend(effect.required_tool_names)
            if effect.denied_runtime_types:
                evaluation.denied_runtimes.extend(effect.denied_runtime_types)
            if effect.preferred_runtime_type and not evaluation.preferred_runtime:
                evaluation.preferred_runtime = effect.preferred_runtime_type
            if effect.force_execution_mode and not evaluation.force_execution_mode:
                evaluation.force_execution_mode = effect.force_execution_mode
            if effect.require_approval:
                evaluation.require_approval = True
                if effect.approval_reason:
                    evaluation.approval_reasons.append(effect.approval_reason)

        # Deduplicate
        evaluation.denied_tools = list(set(evaluation.denied_tools))
        evaluation.required_tools = list(set(evaluation.required_tools))
        evaluation.denied_runtimes = list(set(evaluation.denied_runtimes))

        return evaluation

    # --- Topic Profile registry ---

    def list_topic_profiles(self) -> list[TopicProfile]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM topic_profiles WHERE status = 'active' ORDER BY name")
            ).mappings().fetchall()
        return [self._row_to_topic_profile(r) for r in rows]

    def get_topic_profile_by_name(self, name: str) -> TopicProfile | None:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM topic_profiles WHERE name = :name"),
                {"name": name},
            ).mappings().fetchone()
        return self._row_to_topic_profile(row) if row else None

    def get_user_topic_assignments(self, user_id: str) -> list[UserTopicAssignment]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT * FROM user_topic_assignments
                    WHERE user_id = :user_id AND status = 'active'
                """),
                {"user_id": user_id},
            ).mappings().fetchall()
        return [
            UserTopicAssignment(
                id=str(r["id"]),
                user_id=r["user_id"],
                topic_profile_id=str(r["topic_profile_id"]),
                status=r["status"],
                granted_at=r.get("granted_at"),
                granted_by=r.get("granted_by"),
            )
            for r in rows
        ]

    def resolve_topic_context(self, user_id: str) -> ResolvedTopicContext:
        """Resolve a user's active topic profiles into a merged context."""
        assignments = self.get_user_topic_assignments(user_id)
        if not assignments:
            return ResolvedTopicContext()

        profile_ids = [a.topic_profile_id for a in assignments]

        all_profiles = self.list_topic_profiles()
        active_profiles = [p for p in all_profiles if p.id in profile_ids]

        if not active_profiles:
            return ResolvedTopicContext()

        # Merge allowed resources from all active profiles
        tool_names: set[str] = set()
        conn_names: set[str] = set()
        runtime_types: set[str] = set()
        skill_ids: set[str] = set()
        policy_ids: set[str] = set()

        for profile in active_profiles:
            tool_names.update(profile.allowed_tool_names)
            conn_names.update(profile.allowed_connection_names)
            runtime_types.update(profile.allowed_runtime_types)
            skill_ids.update(profile.active_skill_ids)
            policy_ids.update(profile.active_policy_ids)

        return ResolvedTopicContext(
            profiles=active_profiles,
            allowed_tool_names=sorted(tool_names),
            allowed_connection_names=sorted(conn_names),
            allowed_runtime_types=sorted(runtime_types),
            active_skill_ids=sorted(skill_ids),
            active_policy_ids=sorted(policy_ids),
        )

    # --- Runtime registry ---

    def list_runtimes(self) -> list[RuntimeRecord]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM runtimes WHERE status = 'active' ORDER BY name")
            ).mappings().fetchall()
        return [self._row_to_runtime(r) for r in rows]

    def get_runtime_by_type(self, runtime_type: str) -> RuntimeRecord | None:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM runtimes WHERE type = :type AND status = 'active' LIMIT 1"),
                {"type": runtime_type},
            ).mappings().fetchone()
        return self._row_to_runtime(row) if row else None

    # --- Execution ---

    async def execute(self, req: ExecutionRequest) -> ExecutionResult:
        tool_name = req.tool.tool_name
        runtime_type = TOOL_RUNTIME_MAP.get(tool_name)

        # Resolve topic context for policy evaluation
        topic_profile_ids = None
        if req.user_id:
            topic_ctx = self.resolve_topic_context(req.user_id)
            topic_profile_ids = [p.id for p in topic_ctx.profiles]

        # Resolve connection type for policy matching
        connection_type = None
        connection = self._resolve_connection(req)
        if connection:
            connection_type = connection.type

        # Evaluate policies
        evaluation = self.evaluate_policies(
            tool_name=tool_name,
            connection_type=connection_type,
            topic_profile_ids=topic_profile_ids,
        )

        if evaluation.matched_policies:
            logger.info(
                "Policy evaluation for %s: %d policies matched",
                tool_name, len(evaluation.matched_policies),
            )

        # Check if the tool is denied by policy
        if tool_name in evaluation.denied_tools:
            return ExecutionResult(
                execution_id=req.id,
                status="denied",
                error_message=f"Tool '{tool_name}' is denied by policy",
                policy_evaluation=evaluation.model_dump(),
            )

        # Check if the runtime is denied
        if runtime_type and runtime_type in evaluation.denied_runtimes:
            return ExecutionResult(
                execution_id=req.id,
                status="denied",
                error_message=f"Runtime '{runtime_type}' is denied by policy",
                policy_evaluation=evaluation.model_dump(),
            )

        # Check approval requirement
        if evaluation.require_approval:
            reasons = "; ".join(evaluation.approval_reasons) if evaluation.approval_reasons else "policy requires approval"
            return ExecutionResult(
                execution_id=req.id,
                status="denied",
                error_message=f"Execution requires approval: {reasons}",
                policy_evaluation=evaluation.model_dump(),
            )

        if runtime_type == "sql":
            return await self._execute_sql(req, connection=connection)
        elif runtime_type == "python":
            return await self._execute_python(req)
        else:
            return ExecutionResult(
                execution_id=req.id,
                status="error",
                error_message=f"No runtime mapped for tool: {tool_name}",
            )

    async def _execute_sql(self, req: ExecutionRequest, connection: ConnectionRecord | None = None) -> ExecutionResult:
        # 1. Resolve connection (use pre-resolved if available)
        if connection is None:
            connection = self._resolve_connection(req)
        if connection is None:
            return ExecutionResult(
                execution_id=req.id,
                status="error",
                error_message="Connection not found",
            )

        # 2. Resolve runtime endpoint
        runtime = self.get_runtime_by_type("sql")
        runtime_url = runtime.endpoint_url if runtime else settings.sql_runtime_url

        # 3. Call the SQL runtime
        try:
            parquet_bytes, row_count, columns = await self._call_sql_runtime(
                runtime_url=runtime_url,
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

        # 4. Extract schema from Parquet
        schema_info = self._extract_schema(parquet_bytes)

        # 5. Determine artifact name
        artifact_name = "query_result"
        if req.expected_outputs:
            artifact_name = req.expected_outputs[0].name

        # 6. Register artifact via Artifact Service
        try:
            artifact = await self._register_artifact(
                session_id=req.session_id,
                name=artifact_name,
                parquet_bytes=parquet_bytes,
                schema_info=schema_info,
                row_count=row_count,
                lineage=ArtifactLineage(
                    source_kind="connected_source",
                    connection_id=connection.id,
                    query_text=req.tool.payload.get("query", ""),
                ),
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

    async def _execute_python(self, req: ExecutionRequest) -> ExecutionResult:
        # 1. Resolve runtime endpoint
        runtime = self.get_runtime_by_type("python")
        runtime_url = runtime.endpoint_url if runtime else settings.python_runtime_url

        # 2. Download input artifacts and prepare for the runtime
        inputs = []
        parent_artifact_ids = []
        for inp in req.input_artifacts:
            try:
                parquet_bytes = await self._download_artifact_data(inp.artifact_id)
                alias = inp.alias or inp.artifact_id
                inputs.append({
                    "alias": alias,
                    "data": base64.b64encode(parquet_bytes).decode(),
                })
                parent_artifact_ids.append(inp.artifact_id)
            except Exception as e:
                logger.error("Failed to download artifact %s: %s", inp.artifact_id, e)
                return ExecutionResult(
                    execution_id=req.id,
                    status="error",
                    error_message=f"Failed to load input artifact {inp.artifact_id}: {e}",
                )

        # 3. Call the Python runtime
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{runtime_url}/execute",
                    json={
                        "code": req.tool.payload.get("code", ""),
                        "inputs": inputs,
                    },
                )
                resp.raise_for_status()

            parquet_bytes = resp.content
            row_count = int(resp.headers.get("X-Row-Count", "0"))
        except httpx.HTTPStatusError as e:
            detail = e.response.json().get("detail", str(e)) if e.response else str(e)
            return ExecutionResult(
                execution_id=req.id,
                status="error",
                error_message=f"Python runtime error: {detail}",
            )
        except Exception as e:
            logger.error("Python runtime call failed: %s", e)
            return ExecutionResult(
                execution_id=req.id,
                status="error",
                error_message=str(e),
            )

        # 4. Extract schema
        schema_info = self._extract_schema(parquet_bytes)

        # 5. Determine artifact name
        artifact_name = "transform_result"
        if req.expected_outputs:
            artifact_name = req.expected_outputs[0].name

        # 6. Register artifact
        try:
            artifact = await self._register_artifact(
                session_id=req.session_id,
                name=artifact_name,
                parquet_bytes=parquet_bytes,
                schema_info=schema_info,
                row_count=row_count,
                lineage=ArtifactLineage(
                    source_kind="derived",
                    parent_artifact_ids=parent_artifact_ids,
                    transformation_summary=req.tool.payload.get("code", ""),
                ),
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
        self, runtime_url: str, connection: ConnectionRecord, query: str
    ) -> tuple[bytes, int, list[str]]:
        # Build connection config, injecting credentials if auth is configured
        conn_config = connection.config.model_dump()
        resolved_auth = self._resolve_credentials(connection)
        if resolved_auth:
            conn_config.update(resolved_auth)

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{runtime_url}/execute",
                json={
                    "connection_type": connection.type,
                    "connection_config": conn_config,
                    "query": query,
                },
            )
            resp.raise_for_status()

        row_count = int(resp.headers.get("X-Row-Count", "0"))
        columns = resp.headers.get("X-Columns", "").split(",")
        return resp.content, row_count, columns

    def _resolve_credentials(self, connection: ConnectionRecord) -> dict | None:
        """Resolve credential references into actual values.

        Supports secret_ref auth method: reads values from environment variables.
        Returns a dict to merge into connection_config, or None.
        """
        if not connection.auth_method or not connection.auth_config:
            return None

        resolved = {}
        for key, ref in connection.auth_config.items():
            if isinstance(ref, str) and ref.startswith("env:"):
                env_var = ref[len("env:"):]
                value = os.environ.get(env_var)
                if value:
                    resolved[key] = value
                else:
                    logger.warning("Credential env var %s not set for connection %s", env_var, connection.name)
            # Future: support vault:, ssm:, etc.
        return resolved if resolved else None

    async def _download_artifact_data(self, artifact_id: str) -> bytes:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{settings.artifact_service_url}/artifacts/{artifact_id}/download"
            )
            resp.raise_for_status()
        return resp.content

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
        lineage: ArtifactLineage,
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
            lineage=lineage,
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

        auth_config_raw = row.get("auth_config") or "{}"
        auth_config = json.loads(auth_config_raw) if isinstance(auth_config_raw, str) else auth_config_raw

        return ConnectionRecord(
            id=str(row["id"]),
            name=row["name"],
            display_name=row["display_name"],
            type=row["type"],
            status=row["status"],
            config=ConnectionConfig(**config_dict),
            auth_method=row.get("auth_method"),
            auth_config=auth_config,
            created_at=row["created_at"],
        )

    def _row_to_runtime(self, row) -> RuntimeRecord:
        import json

        capabilities_raw = row["capabilities"]
        capabilities = json.loads(capabilities_raw) if isinstance(capabilities_raw, str) else capabilities_raw

        return RuntimeRecord(
            id=str(row["id"]),
            name=row["name"],
            display_name=row["display_name"],
            type=row["type"],
            endpoint_url=row["endpoint_url"],
            status=row["status"],
            capabilities=capabilities,
            created_at=row["created_at"],
        )

    def _row_to_skill(self, row) -> SkillRecord:
        scope_raw = row.get("scope") or "{}"
        scope_dict = json.loads(scope_raw) if isinstance(scope_raw, str) else scope_raw

        triggers_raw = row.get("triggers") or "[]"
        triggers_list = json.loads(triggers_raw) if isinstance(triggers_raw, str) else triggers_raw

        instructions_raw = row.get("instructions") or "{}"
        instructions_dict = json.loads(instructions_raw) if isinstance(instructions_raw, str) else instructions_raw

        tags_raw = row.get("tags") or "[]"
        tags_list = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        return SkillRecord(
            id=str(row["id"]),
            name=row["name"],
            category=row["category"],
            status=row["status"],
            title=row.get("title"),
            description=row.get("description"),
            scope=SkillScope(**scope_dict),
            triggers=[SkillTrigger(**t) for t in triggers_list],
            instructions=SkillInstructions(**instructions_dict) if instructions_dict else SkillInstructions(summary=""),
            tags=tags_list,
            created_at=row.get("created_at"),
        )

    def _row_to_policy(self, row) -> PolicyRecord:
        scope_raw = row.get("scope") or "{}"
        scope_dict = json.loads(scope_raw) if isinstance(scope_raw, str) else scope_raw

        condition_raw = row.get("condition") or "{}"
        condition_dict = json.loads(condition_raw) if isinstance(condition_raw, str) else condition_raw

        effect_raw = row.get("effect") or "{}"
        effect_dict = json.loads(effect_raw) if isinstance(effect_raw, str) else effect_raw

        tags_raw = row.get("tags") or "[]"
        tags_list = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        return PolicyRecord(
            id=str(row["id"]),
            name=row["name"],
            type=row["type"],
            status=row["status"],
            description=row.get("description"),
            version=row.get("version"),
            scope=PolicyScopeModel(**scope_dict),
            condition=PolicyCondition(**condition_dict),
            effect=PolicyEffect(**effect_dict),
            priority=row.get("priority", 0),
            tags=tags_list,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _row_to_topic_profile(self, row) -> TopicProfile:
        def _parse_json_list(raw) -> list:
            if raw is None:
                return []
            return json.loads(raw) if isinstance(raw, str) else raw

        return TopicProfile(
            id=str(row["id"]),
            name=row["name"],
            display_name=row.get("display_name"),
            description=row.get("description"),
            status=row["status"],
            allowed_tool_names=_parse_json_list(row.get("allowed_tool_names")),
            allowed_connection_names=_parse_json_list(row.get("allowed_connection_names")),
            allowed_runtime_types=_parse_json_list(row.get("allowed_runtime_types")),
            active_skill_ids=_parse_json_list(row.get("active_skill_ids")),
            active_policy_ids=_parse_json_list(row.get("active_policy_ids")),
            domains=_parse_json_list(row.get("domains")),
            tags=_parse_json_list(row.get("tags")),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
