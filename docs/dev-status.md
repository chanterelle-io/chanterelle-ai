# Development Status

## Current Phase: Phase 1 — Core Loop
Status: **Code written, not yet tested end-to-end**

### What's Built (Phase 1)

#### Infrastructure
- [x] `pyproject.toml` with build-system, deps, package discovery
- [x] `docker-compose.yml` — Postgres 16 + MinIO + bucket init
- [x] `db/init.sql` — artifacts + connections tables
- [x] `.env.example` + `.env` configured
- [x] `Makefile` with all service commands
- [x] `shared/settings.py` — centralized config via pydantic-settings
- [x] `shared/db.py` — SQLAlchemy engine singleton

#### Shared Contracts (`shared/contracts/`)
- [x] `artifact.py` — ArtifactRecord, CreateArtifactRequest, TableSchema, ArtifactLineage, etc.
- [x] `connection.py` — ConnectionRecord, ConnectionConfig
- [x] `execution.py` — ExecutionRequest, ExecutionResult, ToolInvocation, ExecutionTarget

#### Artifact Service (`services/artifact/`, port 8002)
- [x] `app.py` — FastAPI: create, get, list, upload, download artifacts
- [x] `catalog.py` — ArtifactCatalog: Postgres CRUD for artifact metadata
- [x] `store.py` — ArtifactStore: MinIO/S3 upload/download

#### SQL Runtime (`services/sql_runtime/`, port 8010)
- [x] `app.py` — FastAPI: /execute endpoint
- [x] `executor.py` — SQLite + PostgreSQL execution → Arrow → Parquet bytes

#### Execution Service (`services/execution/`, port 8001)
- [x] `app.py` — FastAPI: /execute, /connections
- [x] `manager.py` — ExecutionManager: connection resolution, runtime call, artifact registration

#### Agent Service (`services/agent/`, port 8000)
- [x] `app.py` — FastAPI: /chat, /health
- [x] `orchestrator.py` — Tool-use loop (max 5 rounds), system prompt with connections + artifacts
- [x] `session.py` — In-memory session store (Phase 2 will persist)
- [x] `llm/base.py` — LLMProvider ABC, ToolDefinition, ToolCall, ToolResult, Message
- [x] `llm/claude.py` — ClaudeProvider (Anthropic SDK)
- [x] `tools/sql_query.py` — query_sql_source tool definition

#### Seed Data
- [x] `scripts/seed.py` — creates `data/sample.db` (customers, orders, products) + registers `sample_db` connection

### Next Steps to Test Phase 1
1. `make infra` — start Docker services
2. `make seed` — seed sample DB + connection
3. Start all 4 services in separate terminals
4. `curl` to `/chat` endpoint

### Not Built Yet (Phase 2+)
- [ ] Persistent sessions (Postgres-backed)
- [ ] Python runtime
- [ ] Artifact reuse in execution requests (input_artifacts)
- [ ] Skill registry + activation
- [ ] Policy registry + evaluation
- [ ] Topic profiles
- [ ] Deferred execution / Job manager
- [ ] Retention + eviction
- [ ] Workflow definitions

## Sample Data Source
- SQLite at `data/sample.db`
- 200 customers, ~1200 orders, 5 products
- Connection name: `sample_db`
