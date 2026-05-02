# Chanterelle AI — Project Overview

## What
Analytics Agent Platform — session-based analytical workspace where a user interacts with an AI agent to retrieve, analyze, and generate outputs from connected data sources.

## Architecture
- **Agent Service** (port 8000): Orchestration, LLM tool-use loop, session management, session expiration and cleanup
- **Execution Service** (port 8001): Execution request validation, connection registry, runtime registry, skill registry, workflow registry, policy registry, topic profile registry, policy evaluation, runtime routing, credential injection, query analysis, deferred execution (job manager)
- **Artifact Service** (port 8002): Artifact catalog (Postgres), object storage (MinIO/S3), Parquet persistence, retention, pin/unpin, quota tracking, eviction
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
- Artifact retention is session-scoped by default: TTLs, pinning, quota accounting, and eviction are enforced in the Artifact Service
- Agent picks tools/intent; execution manager picks runtime/mode
- Skills (guidance) are separate from tools (actions)
- Active skill summaries are prompt-visible, while detailed skill instructions are fetched on demand with `get_skill_guidance`
- Workflows provide higher-level multi-step guidance on top of skills
- Credentials injected just-in-time, never exposed to agent
- LLM provider is abstracted (`LLMProvider` ABC → `ClaudeProvider` impl)
- Execution service routes to runtimes by tool type (SQL → sql runtime, Python → python runtime)
- Policies evaluated at execution time — can deny tools/runtimes, force deferred mode, require approval
- Topic profiles scope what tools, connections, skills, and workflows a user can access
- Workflow definitions can be resolved by request keywords and active topic-profile workflow ids, then injected into the agent prompt as ordered guidance and policy activation input
- Workflow-scoped policies can now affect execution directly when a matched workflow activates them, including preferred runtime enforcement
- Workflow-required skills can now affect execution directly when a matched workflow requires them for the current turn
- Workflow-preferred tools can now affect execution directly when a matched workflow constrains which execution tools are allowed for that turn
- `/chat` responses now expose matched workflow constraints through `workflow_trace`
- `/chat` responses now also surface deterministic workflow-constraint denial messages when a requested tool or runtime violates the matched workflow
- `GET /sessions/{id}` now exposes persisted message history including workflow traces and workflow denial messages
- `GET /sessions/{id}/workflow-events` now exposes a filtered workflow-audit view backed by dedicated workflow audit storage
- `GET /workflow-audit/events` exposes recent workflow audit events filtered by session or user
- Deferred execution: server-side query analysis triggers background jobs for large/unbounded queries
- Policy conditions are server-side only — agent hints are optional fallback, not the source of truth
- Sessions persisted in Postgres (messages + artifact refs as JSONB) with expiry and cleanup metadata
- Expired-session cleanup coordinates with artifact cleanup: unpinned, non-persistent artifacts are evicted first and pinned artifacts are preserved

## Commands
- `make infra` — start Postgres + MinIO + seed policies + seed topic profiles + seed user assignments
- `make migrate-phase2` — add sessions + runtimes tables to existing DB
- `make migrate-phase3` — add skills table + connection auth columns to existing DB
- `make migrate-phase4` — add policies, topic_profiles, user_topic_assignments tables to existing DB
- `make migrate-phase5` — add jobs table to existing DB
- `make migrate-phase6` — add artifact retention and session lifecycle fields, and backfill seeded topic tool permissions
- `make migrate-phase7` — add workflow registry support to existing DB
- `make migrate-phase8` — add topic-profile workflow allowlists to existing DB
- `make migrate-workflow-audit` — add dedicated workflow audit event storage to existing DB
- `make smoke-mvp` — run the repeatable MVP smoke suite against the live local services
- `make artifact` / `make runtime-sql` / `make runtime-python` / `make execution` / `make agent` — start each service
- `make infra-down` — stop infrastructure

## Spec Documents
- `app-specs/main.md` — full architecture specification
- `app-specs/services.md` — service boundaries and responsibilities
- `app-specs/plan.md` — phased implementation plan
- `app-specs/notes.md` — original design notes
- `app-specs/contracts/` — TypeScript-style interface contracts
