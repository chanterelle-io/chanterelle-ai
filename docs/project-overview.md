# Chanterelle AI — Project Overview

## What
Analytics Agent Platform — session-based analytical workspace where a user interacts with an AI agent to retrieve, analyze, and generate outputs from connected data sources.

## Architecture
- **Agent Service** (port 8000): Orchestration, LLM tool-use loop, session management
- **Execution Service** (port 8001): Execution request validation, connection registry, runtime registry, skill registry, policy registry, topic profile registry, policy evaluation, policy registry, topic profile registry, policy evaluation, runtime routing, credential injection
- **Artifact Service** (port 8002): Artifact catalog (Postgres), object storage (MinIO/S3), Parquet persistence
- **SQL Runtime** (port 8010): Executes SQL against connected sources, returns Parquet
- **Python Runtime** (port 8011): Executes Python transforms on DataFrames, returns Parquet

## Tech Stack
- Python 3.11+, FastAPI, Pydantic
- LLM: Anthropic Claude (swappable via `LLMProvider` abstraction in `services/agent/llm/base.py`)
- Database: PostgreSQL (catalog, connections, sessions)
- Object Storage: MinIO (S3-compatible) for artifact payloads
- Tabular format: Parquet (canonical), Arrow/pandas in-memory
- Infrastructure: Docker Compose (no K8s yet)

## Key Design Decisions
- Artifacts are runtime-independent, stored as Parquet in object storage
- Agent picks tools/intent; execution manager picks runtime/mode
- Skills (guidance) are separate from tools (actions)
- Credentials injected just-in-time, never exposed to agent
- LLM provider is abstracted (`LLMProvider` ABC → `ClaudeProvider` impl)
- Execution service routes to runtimes by tool type (SQL → sql runtime, Python → python runtime)
- Policies evaluated at execution time — can deny tools/runtimes, force deferred mode, require approval
- Topic profiles scope what tools, connections, and skills a user can access
- Policies evaluated at execution time — can deny tools/runtimes, force deferred mode, require approval
- Topic profiles scope what tools, connections, and skills a user can access
- Sessions persisted in Postgres (messages + artifact refs as JSONB)

## Commands
- `make infra` — start Postgres + MinIO + seed policies + seed topic profiles + seed user assignments
- `make migrate-phase2` — add sessions + runtimes tables to existing DB
- `make migrate-phase3` — add skills table + connection auth columns to existing DB
- `make migrate-phase4` — add policies, topic_profiles, user_topic_assignments tableister runtimes + seed skills + seed policies + seed topic profiles + seed user assignments
- `make migrate-phase2` — add sessions + runtimes tables to existing DB
- `make migrate-phase3` — add skills table + connection auth columns to existing DB
- `make migrate-phase4` — add policies, topic_profiles, user_topic_assignments tables to existing DB
- `make artifact` / `make runtime-sql` / `make runtime-python` / `make execution` / `make agent` — start each service
- `make infra-down` — stop infrastructure

## Spec Documents
- `app-specs/main.md` — full architecture specification
- `app-specs/services.md` — service boundaries and responsibilities
- `app-specs/plan.md` — phased implementation plan
- `app-specs/notes.md` — original design notes
- `app-specs/contracts/` — TypeScript-style interface contracts
