# Implementation Plan

This plan builds toward the MVP defined in [main.md](main.md), section 21. It is organized into phases, where each phase produces a working, testable slice of the system. Later phases build on earlier ones but each phase has a clear vertical deliverable — not just "set up infrastructure."

The driving principle: **get to a working agent-to-runtime-to-artifact loop as early as possible**, then layer on governance, skills, policies, and UX incrementally.

---

## Phase 0 — Project Foundation

**Goal:** Establish the repo structure, tooling, and local development environment so all subsequent work lands in the right shape.

### Deliverables

- Monorepo structure with workspace/package layout for the MVP deployables:
  - `agent-service` — orchestration, session, BFF
  - `execution-service` — execution manager, connection registry, runtime registry, job manager
  - `artifact-service` — artifact catalog, object storage interface
  - `shared` — contracts, types, shared utilities
- Technology decisions documented:
  - Language/runtime (e.g., TypeScript/Node, Python, or both)
  - Database (e.g., PostgreSQL for relational state)
  - Object storage (e.g., S3-compatible, MinIO for local dev)
  - Message/event transport if needed for job completion (e.g., simple polling for MVP, or lightweight queue)
  - LLM provider and client library for the agent
- Local dev environment:
  - Docker Compose for Postgres + MinIO (or equivalent)
  - Seed scripts for initial data
- CI pipeline skeleton (lint, type-check, test)

### Decision point

Choose the tech stack before writing any service code. This phase is purely scaffolding and decisions.

---

## Phase 1 — The Core Loop (Artifact Store + One Runtime + Agent Shell)

**Goal:** A user sends a natural language request, the agent calls a SQL tool, a SQL runtime executes the query against a real database, and the result is persisted as a Parquet artifact with schema metadata. This is the minimum viable proof of the architecture.

### 1.1 Artifact Service — foundation

- Implement the Artifact contract ([artifact-contract.md](contracts/artifact-contract.md))
- Object storage write/read (Parquet files to MinIO/S3)
- Artifact catalog: create artifact record, store schema + basic metadata
- Artifact lookup by ID
- No retention, no lineage, no previews yet

### 1.2 Connection Registry — minimal

- Implement the Connection contract ([connection-contract.md](contracts/connection-contract.md))
- CRUD for connection definitions
- Store one seed connection (e.g., a local PostgreSQL with sample data)
- Auth references stored but no credential injection yet — use hard-coded config for Phase 1

### 1.3 SQL Runtime — first runtime

- Implement a basic SQL runtime that:
  - Accepts an execution request (query + connection details)
  - Connects to the target database
  - Executes the query
  - Returns results as Arrow/Parquet
- Runs as a separate process or container
- No runtime registry, no provisioning — single static instance for Phase 1

### 1.4 Execution Service — skeleton

- Accept an execution request
- Resolve the target connection from the Connection Registry
- Route to the SQL runtime (hardcoded, no policy evaluation yet)
- Receive results
- Write Parquet to Artifact Store
- Register artifact in Artifact Catalog
- Return artifact reference

### 1.5 Agent Service — shell

- Agent API endpoint: receive a user message, return a response
- LLM integration with tool-use: the agent has one tool ("query SQL source")
- Agent forms an execution request from the user's natural language
- Agent submits to Execution Service
- Agent receives artifact reference, inspects metadata, responds with summary
- Session: in-memory for Phase 1 (conversation history + artifact references list)

### Phase 1 test

User says: "Show me all customers who signed up last month."
Agent calls SQL tool → Execution Service → SQL runtime → Postgres → Parquet in object storage → artifact registered → agent returns "Here are 342 customers..." with column summary.

---

## Phase 2 — Session State + Artifact Reuse + Python Runtime

**Goal:** The system can remember prior artifacts and reuse them. A second runtime (Python) exists. The user can do multi-step analysis.

### 2.1 Session Manager — persistent state

- Session creation and persistence (Postgres)
- Store: session metadata, conversation history, artifact references, active connection bindings
- Agent loads session context on each turn

### 2.2 Artifact reuse

- Agent can look up prior session artifacts by name or description
- Artifact catalog: list artifacts for a session, filter by type
- Execution requests can include `inputArtifacts` — the runtime loads them from object storage
- Lineage: new artifacts track `parentArtifactIds` and `transformationSummary`

### 2.3 Python Runtime

- A Python runtime that:
  - Accepts an execution request with code/operation + input artifact references
  - Loads input artifacts as DataFrames (from Parquet)
  - Executes the operation (filtering, transformation, aggregation)
  - Writes output as Parquet
- Runs as a separate container

### 2.4 Runtime Registry — basic

- Store runtime definitions (SQL runtime, Python runtime)
- Execution Service selects runtime by matching the tool's required runtime type
- Still single static instances, no dynamic provisioning

### 2.5 Agent tool expansion

- Agent now has two tools: "query SQL source" and "transform with Python"
- Agent can chain: SQL result → Python transformation
- Agent references prior artifacts in its planning

### Phase 2 test

Reproduce the churn scenario (section 18 of main.md) — at least the first 2 steps:
1. "Get customers from last 6 months" → SQL → `customers_last_6_months`
2. "Keep only those inactive in the last 30 days" → Python loads artifact, filters → `potential_churn_customers`

---

## Phase 3 — Skills + Credential Injection + Schema Inspection

**Goal:** The agent uses skills to improve its behavior, credentials are injected properly, and the agent can inspect artifact schemas before acting.

### 3.1 Skill Registry

- Implement the Skill contract ([skill-contract.md](contracts/skill-contract.md))
- Store skills with scope (global, connection-level)
- Seed a connector skill for the SQL source (schema conventions, safe join patterns)
- Seed a metric skill (e.g., "how to calculate churn")

### 3.2 Skill activation in the agent

- On each turn, the agent resolves applicable skills based on:
  - Involved connections
  - Task keywords
  - Scope matching
- Skills are injected into the agent's context/prompt before planning
- Start with: connector skills + one metric skill

### 3.3 Credential injection

- Secret Manager integration (Vault, env-based, or a simple encrypted store for MVP)
- Connection auth references resolved at execution time
- Credentials injected into the runtime as environment variables or connection strings
- Scoped to the execution (ephemeral by default)
- Remove hardcoded credentials from Phase 1

### 3.4 Artifact schema inspection

- Agent can query artifact metadata: columns, types, row counts, time columns
- Agent uses this to decide whether to reuse an artifact, filter it, or re-query
- Artifact catalog exposes a metadata endpoint

### Phase 3 test

User asks about revenue. Agent activates the revenue metric skill, queries the right columns per skill instructions, validates the result matches the skill's output expectations.

---

## Phase 4 — Policies + Topic Profiles + Execution Routing

**Goal:** The platform enforces policies, routes execution based on rules (not just agent preference), and users operate within topic profiles.

### 4.1 Policy Registry

- Implement the Policy contract ([policy-contract.md](contracts/policy-contract.md))
- Store policies with scope and priority
- Seed execution routing policies:
  - "If estimated rows > threshold, prefer async"
  - "Restricted sources require isolated runtime"

### 4.2 Execution policy evaluation

- Execution Service evaluates policies before selecting runtime and mode
- Policies can override the agent's requested runtime type
- Policies can force deferred mode

### 4.3 Topic Profile Registry

- Implement the Topic Profile and UserTopicAssignment contracts ([topic-contract.md](contracts/topic-contract.md))
- Store topic profiles with allowed tools, skills, connections, policies
- Store user-topic assignments
- Seed at least 2 profiles (e.g., "Finance Analysis", "General Exploration")

### 4.4 Topic resolution in the agent

- On each turn, agent resolves applicable topic profiles:
  - Get user's allowed topics
  - Infer relevant topics from request
  - Intersect
- Activate only the tools, skills, and policies from the resolved set
- Log topic activation per turn

### Phase 4 test

User assigned to "Finance Analysis" topic asks a question that would require a tool not in that profile. Agent correctly does not use it. A policy forces a large query to deferred mode despite the agent preferring interactive.

---

## Phase 5 — Deferred Execution + Job Manager

**Goal:** Long-running or large-scale work is tracked as a job. Users can check status and get results when ready.

### 5.1 Job Manager

- Job creation, status tracking (submitted, running, failed, completed)
- Log collection from runtimes
- Completion callbacks: register output artifacts on job success
- Job lookup by session

### 5.2 Execution Service async path

- When execution policy classifies workload as deferred:
  - Create job record
  - Submit to runtime asynchronously
  - Return job reference to agent immediately
- Agent responds: "I've started that analysis. I'll let you know when it's ready."

### 5.3 Job status and completion in agent

- Agent can check job status on subsequent turns
- On completion: agent retrieves the artifact, summarizes results
- Session state tracks pending and completed jobs

### 5.4 Runtime provisioning — basic

- Runtime Service can create new runtime instances on demand (container-based)
- Session-scoped or task-scoped binding
- Reuse compatible idle instances

### Phase 5 test

User requests a wide date-range analysis. Policy routes to deferred. Job is created. User asks "Is my analysis done?" → Agent checks job status → Eventually returns results.

---

## Phase 6 — Retention + Previews + Polish

**Goal:** The system manages its own storage, provides rich artifact previews, and handles the rough edges.

### 6.1 Retention

- Implement retention classes (temporary, reusable, pinned, persistent)
- Workspace quota tracking
- Automatic eviction following the priority order
- User pinning/unpinning via agent commands

Recommended implementation order:
1. Retention metadata and defaults
2. Pin/unpin flows
3. Quota accounting and eviction candidate selection
4. Automatic eviction

#### 6.1.1 Retention model foundation

- Extend artifact metadata with retention fields such as retention class, pinned state, expires-at, and last-accessed-at
- Apply retention defaults when artifacts are created based on artifact type, producing tool, or workflow context
- Update access timestamps on artifact reads so eviction decisions can use recent usage rather than creation time alone
- Expose retention metadata in artifact catalog responses so the agent and future UI can explain lifecycle state

#### 6.1.2 Pin/unpin flows

- Add artifact-service operations to pin and unpin an artifact explicitly
- Support user-facing agent commands such as "pin this artifact" and "unpin that table from earlier"
- Treat pinning as an override on top of the retention class rather than a separate storage path
- Surface pin state in artifact metadata and agent responses so users can see what is protected from cleanup

#### 6.1.3 Quota tracking and eviction planning

- Track storage usage at the workspace level and expose current usage versus quota
- Define eviction priority using retention class, expiration state, pin state, and recency of access
- Add a way to list eviction candidates before deletion so behavior can be validated safely
- Keep catalog state and object-store deletion in sync when an artifact is evicted

#### 6.1.4 Automatic eviction

- Run cleanup on a scheduled or on-write basis when quota or retention thresholds are exceeded
- Skip pinned and persistent artifacts unless an explicit administrative policy says otherwise
- Record eviction reason and timestamps for debugging and user-facing explanations

### Phase 6.1 test

1. User creates multiple temporary and reusable artifacts until the workspace exceeds quota.
2. User pins one artifact that would otherwise be eligible for cleanup.
3. Eviction removes the correct unpinned artifacts in priority order while preserving the pinned artifact.
4. User unpins the protected artifact, and it becomes eligible under the normal retention rules on the next cleanup pass.

### 6.2 Artifact previews

- Generate sample row previews when artifacts are created
- Store preview URIs in the artifact catalog
- Agent can show preview data inline in responses

### 6.3 Agent UX improvements

- Better natural language artifact referencing ("that table from earlier", "the customer dataset")
- Chart generation tool (if not already added)
- Export support (CSV, Excel download links)
- Error handling and user-facing explanations when things fail

### 6.4 Session lifecycle

- Session expiration and cleanup
- Session resume on reconnect

---

## Phase 7 — Workflow Definitions + Advanced Skills + Multi-Scope Governance

**Goal:** The system supports structured multi-step workflows, richer skill scopes, and organization-level governance.

### 7.1 Workflow Registry

- Implement the Workflow Definition contract ([workflow-contract.md](contracts/workflow-contract.md))
- Store workflow definitions with triggers and steps
- Seed one workflow (e.g., churn analysis workflow)
- Agent detects when a request matches a workflow trigger and follows the step sequence

### 7.2 Advanced skill scoping

- Skills at workspace, domain, and session levels
- Session-level skill learning (user preferences inferred during conversation)
- **Tool-based skill pull:** Replace full-injection with a two-tier model:
  - System prompt includes only skill name + one-line summary for all matched skills (~50 tokens each)
  - New `get_skill_guidance(skill_name)` tool returns full instructions (recommended steps, dos/donts, output expectations) on demand
  - LLM decides if/when it needs detailed guidance — simple questions skip the tool entirely
  - Scales to hundreds of skills without prompt bloat or mandatory extra latency

### 7.3 Workspace-level governance

- Workspace policies and workspace-scoped topic profiles
- Multi-tenant considerations if relevant

---

## What's Not in This Plan

These are from the architecture spec but explicitly deferred beyond MVP:

- **Managed-table promotion** (Delta/Iceberg) — add when datasets need incremental updates or production sharing
- **Distributed big-data runtimes** (Spark) — add when interactive runtimes can't handle the workload
- **Rich audit and compliance** — start with turn-level topic activation logs, expand later
- **Dynamic topic switching mid-session** — start with per-session topic, upgrade later
- **Multiple workspace/organization support** — start single-tenant

---

## Phase Dependencies

```
Phase 0  (foundation)
  │
  ▼
Phase 1  (core loop: agent → execution → runtime → artifact)
  │
  ▼
Phase 2  (session state, artifact reuse, Python runtime)
  │
  ├──────────────────┐
  ▼                  ▼
Phase 3            Phase 4
(skills,           (policies, topics,
 credentials,       execution routing)
 schema inspection)
  │                  │
  └────────┬─────────┘
           ▼
         Phase 5  (deferred execution, jobs)
           │
           ▼
         Phase 6  (retention, previews, polish)
           │
           ▼
         Phase 7  (workflows, advanced skills, governance)
```

Phases 3 and 4 can be worked in parallel by separate tracks once Phase 2 is complete.

---

## Rough Effort Shape

| Phase | Relative weight | What it proves |
|-------|----------------|----------------|
| 0 | Light | Decisions made, repo ready |
| 1 | **Heavy** | Architecture works end-to-end |
| 2 | Medium | Multi-step analytics work |
| 3 | Medium | Agent quality improves with skills |
| 4 | Medium | Governance model works |
| 5 | Medium | Async workloads handled |
| 6 | Light–Medium | Production readiness |
| 7 | Medium | Advanced orchestration |

Phase 1 is the hardest because it forces every layer to exist for the first time, even in minimal form. After that, each phase extends an already-working system.