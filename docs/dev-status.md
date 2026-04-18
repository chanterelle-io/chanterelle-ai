# Development Status

## Phase 1 — Core Loop ✓
Status: **Complete — tested end-to-end**

Agent → SQL tool → Execution Service → SQL Runtime → Postgres → Parquet in MinIO → artifact registered → agent returns summary.

## Phase 2 — Session State + Artifact Reuse + Python Runtime ✓
Status: **Complete — tested end-to-end**

### What's Built

#### Infrastructure
- [x] `pyproject.toml` with build-system, deps, package discovery (pandas added in Phase 2)
- [x] `docker-compose.yml` — Postgres 16 + MinIO + bucket init
- [x] `db/init.sql` — artifacts, connections, sessions, runtimes tables
- [x] `scripts/migrate_phase2.py` — migration for existing DBs (sessions + runtimes tables)
- [x] `.env.example` + `.env` configured
- [x] `Makefile` with all service commands (runtime-python, migrate-phase2 added in Phase 2)
- [x] `shared/settings.py` — centralized config via pydantic-settings (python_runtime_url added)
- [x] `shared/db.py` — SQLAlchemy engine singleton

#### Shared Contracts (`shared/contracts/`)
- [x] `artifact.py` — ArtifactRecord, CreateArtifactRequest, TableSchema, ArtifactLineage, etc.
- [x] `connection.py` — ConnectionRecord, ConnectionConfig
- [x] `execution.py` — ExecutionRequest, ExecutionResult, ToolInvocation, ExecutionTarget, ExecutionArtifactInput
- [x] `runtime.py` — RuntimeRecord (Phase 2)

#### Artifact Service (`services/artifact/`, port 8002)
- [x] `app.py` — FastAPI: create, get, list, upload, download artifacts
- [x] `catalog.py` — ArtifactCatalog: Postgres CRUD for artifact metadata
- [x] `store.py` — ArtifactStore: MinIO/S3 upload/download

#### SQL Runtime (`services/sql_runtime/`, port 8010)
- [x] `app.py` — FastAPI: /execute endpoint
- [x] `executor.py` — SQLite + PostgreSQL execution → Arrow → Parquet bytes

#### Python Runtime (`services/python_runtime/`, port 8011) — Phase 2
- [x] `app.py` — FastAPI: /execute, /health
- [x] `executor.py` — Executes Python code on pandas DataFrames, restricted builtins, returns Parquet

#### Execution Service (`services/execution/`, port 8001)
- [x] `app.py` — FastAPI: /execute, /connections, /runtimes, /skills, /skills/resolve
- [x] `manager.py` — ExecutionManager: connection resolution, runtime registry, skill registry, tool→runtime routing, credential injection, artifact download for input_artifacts, lineage tracking

#### Agent Service (`services/agent/`, port 8000)
- [x] `app.py` — FastAPI: /chat, /health
- [x] `orchestrator.py` — Tool-use loop (max 15 rounds), system prompt with connections + artifacts + skills, dispatches to SQL, Python, and inspect tools, saves session after each turn
- [x] `session.py` — Postgres-backed session store (upgraded from in-memory in Phase 2)
- [x] `llm/base.py` — LLMProvider ABC, ToolDefinition, ToolCall, ToolResult, Message
- [x] `llm/claude.py` — ClaudeProvider (Anthropic SDK)
- [x] `tools/sql_query.py` — query_sql_source tool definition
- [x] `tools/python_transform.py` — transform_with_python tool definition (Phase 2)
- [x] `tools/inspect_artifact.py` — inspect_artifact tool definition (Phase 3)

#### Seed Data
- [x] `scripts/seed.py` — creates `data/sample.db` (customers, orders, products) + registers `sample_db` connection + registers runtimes + seeds skills

### Not Built Yet (Phase 5+)iction
- [ ] Workflow definitions

### Known Limitations
- Python runtime uses `exec()` with restricted builtins but no full sandbox
- Credential injection supports `env:` refs only (vault/SSM planned)

## Phase 3 — Skills + Credential Injection + Artifact Inspection ✓
Status: **Complete — tested end-to-end**

### What's Built

#### DB Schema
- [x] `skills` table in `db/init.sql` (id, name, category, status, title, description, scope, triggers, instructions, tags)
- [x] `auth_method` + `auth_config` columns added to `connections` table
- [x] `scripts/migrate_phase3.py` — migration for existing DBs

#### Shared Contracts
- [x] `shared/contracts/skill.py` — SkillRecord, SkillScope, SkillTrigger, SkillInstructions, SkillCategory
- [x] `shared/contracts/connection.py` — added `auth_method` + `auth_config` fields to ConnectionRecord

#### 3.1 Skill Registry (Execution Service)
- [x] `manager.py` — `list_skills()`, `get_skills_for_context()` (scope + trigger matching)
- [x] `app.py` — `GET /skills`, `GET /skills/resolve?connection_names=&user_message=`
- [x] Row-to-model conversion with JSON parsing for scope, triggers, instructions, tags

#### 3.2 Skill Activation (Agent)
- [x] `orchestrator.py` — fetches skills via `/skills/resolve`, injects instructions into system prompt
- [x] Skills section in prompt includes summary, recommended_steps, dos/donts, output_expectations

#### 3.3 Credential Injection
- [x] `manager.py` — `_resolve_credentials()` reads `env:VAR_NAME` refs from `auth_config`
- [x] `_call_sql_runtime()` merges resolved credentials into connection config at execution time
- [x] No plaintext credentials stored in DB — only references

#### 3.4 Artifact Schema Inspection
- [x] `tools/inspect_artifact.py` — tool definition (name, columns, sample rows)
- [x] `orchestrator.py` — `_execute_inspect_artifact()` downloads Parquet, reads sample rows via pyarrow+pandas
- [x] Agent can now answer follow-up questions about data values without re-querying

#### Seed Data
- [x] `scripts/seed.py` — seeds two skills: `sample_db_connector` (connector) and `churn_analysis` (metric)

## Phase 4 — Policies + Topic Profiles + Execution Routing ✓
Status: **Complete — tested end-to-end**
Phase 4 — Policies + Topic Profiles + Execution Routing ✓
Status: **Complete — tested end-to-end**

### What's Built

#### DB Schema
- [x] `policies` table in `db/init.sql` (id, name, type, status, description, scope, condition, effect, priority, tags)
- [x] `topic_profiles` table (id, name, display_name, description, allowed_tool_names, allowed_connection_names, allowed_runtime_types, active_skill_ids, active_policy_ids, domains, tags)
- [x] `user_topic_assignments` table (id, user_id, topic_profile_id, status, granted_at, granted_by)
- [x] `scripts/migrate_phase4.py` — migration for existing DBs

#### Shared Contracts
- [x] `shared/contracts/policy.py` — PolicyRecord, PolicyType, PolicyStatus, PolicyScope, PolicyCondition, PolicyEffect, PolicyEvaluation
- [x] `shared/contracts/topic.py` — TopicProfile, UserTopicAssignment, ResolvedTopicContext
- [x] `shared/contracts/execution.py` — added `user_id` to ExecutionRequest, `policy_evaluation` + `denied` status to ExecutionResult

#### 4.1 Policy Registry (Execution Service)
- [x] `manager.py` — `list_policies()`, `get_policies_for_context()`, `evaluate_policies()`
- [x] Policy matching by scope (global, topic-profile-linked), condition (tool_names, source_types, row count thresholds)
- [x] Merged effects: denied tools, denied runtimes, forced execution mode, approval gates
- [x] `app.py` — `GET /policies`, `GET /policies/evaluate`

#### 4.2 Execution Policy Evaluation
- [x] `execute()` evaluates policies before calling runtimes
- [x] Returns `status: "denied"` with policy details when blocked
- [x] Checks denied tools, denied runtimes, and approval requirements

#### 4.3 Topic Profile Registry (Execution Service)
- [x] `manager.py` — `list_topic_profiles()`, `get_user_topic_assignments()`, `resolve_topic_context()`
- [x] Merges all active profiles for a user into `ResolvedTopicContext`
- [x] `app.py` — `GET /topics`, `GET /topics/resolve?user_id=`

#### 4.4 Topic Resolution in Agent
- [x] `/chat` accepts optional `user_id` (backward compatible — no user_id = full access)
- [x] `orchestrator.py` — fetches topic context, filters connections, tools, and skills by profile
- [x] System prompt includes active topic profile names and constraints
- [x] `user_id` passed through to ExecutionRequest for server-side policy enforcement
- [x] Denied execution results handled gracefully in tool responses

#### Seed Data
- [x] 2 policies: `deny_python_for_finance` (tool_selection), `large_query_advisory` (execution_routing)
- [x] 2 topic profiles: `finance_analysis` (SQL + inspect only), `general_exploration` (full access)
- [x] 2 user assignments: `finance-user` → finance_analysis, `analyst-user` → general_exploration

## 
### What's Built

#### DB Schema
- [x] `policies` table in `db/init.sql` (id, name, type, status, description, scope, condition, effect, priority, tags)
- [x] `topic_profiles` table (id, name, display_name, description, allowed_tool_names, allowed_connection_names, allowed_runtime_types, active_skill_ids, active_policy_ids, domains, tags)
- [x] `user_topic_assignments` table (id, user_id, topic_profile_id, status, granted_at, granted_by)
- [x] `scripts/migrate_phase4.py` — migration for existing DBs

#### Shared Contracts
- [x] `shared/contracts/policy.py` — PolicyRecord, PolicyType, PolicyStatus, PolicyScope, PolicyCondition, PolicyEffect, PolicyEvaluation
- [x] `shared/contracts/topic.py` — TopicProfile, UserTopicAssignment, ResolvedTopicContext
- [x] `shared/contracts/execution.py` — added `user_id` to ExecutionRequest, `policy_evaluation` + `denied` status to ExecutionResult

#### 4.1 Policy Registry (Execution Service)
- [x] `manager.py` — `list_policies()`, `get_policies_for_context()`, `evaluate_policies()`
- [x] Policy matching by scope (global, topic-profile-linked), condition (tool_names, source_types, row count thresholds)
- [x] Merged effects: denied tools, denied runtimes, forced execution mode, approval gates
- [x] `app.py` — `GET /policies`, `GET /policies/evaluate`

#### 4.2 Execution Policy Evaluation
- [x] `execute()` evaluates policies before calling runtimes
- [x] Returns `status: "denied"` with policy details when blocked
- [x] Checks denied tools, denied runtimes, and approval requirements

#### 4.3 Topic Profile Registry (Execution Service)
- [x] `manager.py` — `list_topic_profiles()`, `get_user_topic_assignments()`, `resolve_topic_context()`
- [x] Merges all active profiles for a user into `ResolvedTopicContext`
- [x] `app.py` — `GET /topics`, `GET /topics/resolve?user_id=`

#### 4.4 Topic Resolution in Agent
- [x] `/chat` accepts optional `user_id` (backward compatible — no user_id = full access)
- [x] `orchestrator.py` — fetches topic context, filters connections, tools, and skills by profile
- [x] System prompt includes active topic profile names and constraints
- [x] `user_id` passed through to ExecutionRequest for server-side policy enforcement
- [x] Denied execution results handled gracefully in tool responses

#### Seed Data
- [x] 2 policies: `deny_python_for_finance` (tool_selection), `large_query_advisory` (execution_routing)
- [x] 2 topic profiles: `finance_analysis` (SQL + inspect only), `general_exploration` (full access)
- [x] 2 user assignments: `finance-user` → finance_analysis, `analyst-user` → general_exploration

## Sample Data Source
- SQLite at `data/sample.db`
- 200 customers, ~1200 orders, 5 products
- Connection name: `sample_db`
