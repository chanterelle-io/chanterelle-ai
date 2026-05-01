# Chanterelle — System Overview

## What is Chanterelle?

Chanterelle is a session-based analytics platform where a user interacts with an AI agent to retrieve, analyze, and generate outputs from connected data sources. The user talks in natural language; the platform handles SQL execution, result storage, and multi-step analytical workflows behind the scenes.

## How it works

The user sends a message. The agent (powered by an LLM) interprets the request, writes a SQL query, and hands it off to the platform. The platform runs the query against the right data source, stores the result as a reusable artifact, and returns a summary to the user. On follow-up questions, the agent can reference prior artifacts — loading them into a Python runtime for filtering, aggregation, or transformation — building analysis step by step.

```
User
  │
  ▼
Agent Service ──── "What do we have? What should I do?"
  │                    │                    │
  │              reads artifacts      reads connections
  │              + inspects data      + resolves skills
  │                                  + resolves workflows
  │                                  + resolves topic profiles
  │                    │                    │
  │              Artifact Service    Execution Service
  │                                        │
  │                                  evaluates policies
  │                                  picks runtime
  │                                  resolves connection
  │                                  injects credentials
  │                                  loads input artifacts
  │                                        │
  │                              ┌─────────┴─────────┐
  │                              │                   │
  │                         SQL Runtime       Python Runtime
  │                              │                   │
  │                         Data Source        Input DataFrames
  │                              │                   │
  │                              └─────────┬─────────┘
  │                                  Parquet result
  │                                        │
  │                              stores in Artifact Service
  │                                        │
  ▼                                        ▼
User sees summary                  Artifact available
                                   for future steps
```

## The five services

### Agent Service (port 8000)

The brain. Receives user messages, talks to the LLM, decides which tools to use, and composes the response.

On each turn:
1. Loads the session (or creates a new one)
2. If a `user_id` is provided, resolves the user's **topic profiles** — which tools, connections, skills, and workflows they're allowed to use
3. Filters connections and fetches applicable skills and workflows, including topic-profile workflow allowlists when present
4. Builds a system prompt with connections, artifacts, the active tool list for that turn, skill instructions, workflow guidance, and topic constraints
5. Sends the conversation to the LLM (only the tools allowed by the topic profile)
6. If the LLM calls a tool (e.g. `query_sql_source`, `transform_with_python`, `inspect_artifact`, `pin_artifact`, or `unpin_artifact`), the agent executes it by calling the Execution Service or Artifact Service
7. Feeds the tool result back to the LLM (including policy denial or deferred messages)
8. If the execution was deferred, the agent stops the tool loop and reports the job ID to the user
9. Returns the LLM's final response to the user
10. Persists the updated session (messages + artifact references) to Postgres

The LLM provider is abstracted — currently Claude, swappable to any provider by implementing the `LLMProvider` interface.

**Tools available:**
- `query_sql_source` — execute SQL against a connected data source
- `transform_with_python` — run Python code on existing artifacts (loaded as pandas DataFrames)
- `inspect_artifact` — read sample rows and column details from an existing artifact without re-querying
- `pin_artifact` — protect an existing artifact from automatic cleanup
- `unpin_artifact` — remove that cleanup protection and return the artifact to normal retention handling
- `check_job_status` — check the status of a deferred background job

### Execution Service (port 8001)

The dispatcher. Sits between the agent and the runtimes. The agent never talks to runtimes directly.

When a tool call comes in, the execution service:
1. **Resolves the connection** (for SQL) — looks up the connection name in the registry (Postgres), gets the type, host, path, and config
2. **Picks the runtime** — matches the tool to a runtime type via the runtime registry (e.g. `query_sql` → sql runtime, `python_transform` → python runtime)
3. **Loads input artifacts** (for Python transforms) — downloads Parquet from Artifact Service and base64-encodes for the runtime
4. **Calls the runtime** — sends the request over HTTP**skill registry**, **policy registry**, and **topic profile registry** — all stored in Postgres.

Before executing, it evaluates **policies** against the request context (tool, connection type, user's topic profiles, and any explicitly activated workflow policies). Policies can deny tools, deny runtimes, force deferred execution, or require approval. If a policy blocks the request, the execution service returns a `denied` status instead of running anything
5. **Handles the output** — takes the Parquet bytes from the runtime, registers the artifact via the Artifact Service (with lineage — source connection or parent artifacts), returns the artifact ID

It owns the **connection registry**, **runtime registry**, **skill registry**, **workflow registry**, **policy registry**, and **topic profile registry** — all stored in Postgres.

Before executing, it evaluates **policies** against the request context (tool, connection type, user's topic profiles, and any matched workflow policy ids). Policies can deny tools, deny runtimes, force deferred execution, or require approval. If a policy blocks the request, the execution service returns a `denied` status instead of running anything.

### Artifact Service (port 8002)

The data librarian. Owns two things:

- **Catalog** (Postgres) — metadata about every artifact: name, schema (columns + types), row count, byte size, lineage (which connection, what query produced it), retention class, pin state, expiration, last access time, and eviction details
- **Store** (MinIO/S3) — the actual Parquet files

When a query produces a table:
1. A catalog record is created with all metadata
2. The Parquet file is uploaded to object storage
3. A cached preview of the first few rows is generated and stored with the artifact metadata
4. The upload path checks session quota and cleanup rules. Expired or lower-priority unpinned artifacts may be evicted if needed, while pinned artifacts are preserved
5. The artifact is now available for future steps — the agent can inspect its schema, reuse the cached preview, show preview rows in normal result summaries, a Python runtime can load it, or the user can download it

It answers questions like: "What artifacts exist?", "What columns does `customers_last_month` have?", "Show me a few sample rows.", "Give me the Parquet bytes.", "How much quota is this session using?", and "Which artifacts are eligible for cleanup?"

### SQL Runtime (port 8010)

The worker. Receives a SQL query + connection config, executes it against the actual data source, and returns the result as Parquet bytes.

Currently supports SQLite and PostgreSQL. The runtime is stateless — it doesn't store results or track sessions. It just runs queries and returns data.
Also exposes a `POST /analyze` endpoint for lightweight query analysis — extracts source table names, looks up row counts (SQLite: `COUNT(*)` per table; PostgreSQL: `pg_stat_user_tables.n_live_tup`), and detects WHERE/LIMIT clauses. This is used by the Execution Service for policy evaluation without running the actual query.
### Python Runtime (port 8011)

The transformer. Receives Python code + input artifacts (as base64-encoded Parquet), loads them as pandas DataFrames, executes the code, and returns the result as Parquet bytes.

Used when the agent needs to filter, aggregate, or transform data from a previous step. The code must assign the output to a `result` variable (a DataFrame). Runs with restricted builtins for safety.

Like the SQL runtime, this is stateless and isolated.

## Key concepts

### Artifacts

An artifact is a saved result — typically a table (Parquet file) but could also be a chart, file, or report. Artifacts are:
- **Runtime-independent** — stored in object storage, not tied to any execution environment
- **Reusable** — the agent can reference them in later steps
- **Tracked** — schema, lineage, statistics, preview rows, retention metadata, and cleanup status are recorded in the catalog

Artifacts now participate in a retention model:
- **Retention classes** determine the default lifecycle (`temporary`, `reusable`, `pinned`, `persistent`)
- **Pinning** protects an artifact from automatic cleanup until it is explicitly unpinned
- **Expiration** is tracked per artifact using `expires_at`; reads also refresh `last_accessed_at` so cleanup decisions can factor in recent usage
- **Quota** is the storage budget for a session. The system tracks how many artifact bytes a session is currently using and compares that against a configured limit
- **Quota enforcement** is session-scoped; the Artifact Service can report quota usage, list eviction candidates, and evict eligible artifacts when a session exceeds its storage budget. Quota eviction responses now also report `preserved_artifacts` for pinned or otherwise non-evictable items that remain
- **Eviction** applies only to unpinned, non-persistent artifacts. The system records why something was evicted, such as expired retention or quota pressure. A session can remain over quota after an eviction attempt when only pinned or otherwise preserved artifacts are left
- **Session cleanup coordination** means expired-session cleanup in the Agent Service now triggers Artifact Service cleanup for that session first. Unpinned, non-persistent artifacts are evicted with a `session_expired` reason before the session record is removed; pinned and persistent artifacts are preserved. The cleanup response now reports per-session evicted artifact ids plus `preserved_artifacts` with explicit reasons such as `pinned`, and leaves the session row in place if strict artifact cleanup fails

### Connections

A connection defines how to reach a data source: type (SQLite, PostgreSQL, etc.), endpoint config, and authentication references. Connections don't own runtimes — they just describe where data lives. Credentials are stored as references (e.g. `env:VAR_NAME`) and resolved at execution time — never exposed to the agent or stored in plaintext.

### Sessions

A session is the workspace for a conversation. It tracks: messages, artifacts produced, and which connections are accessible. Persisted in Postgres (messages and artifact references stored as JSONB). Sessions survive service restarts, but they now also have lifecycle metadata:
- `last_accessed_at` is refreshed when the session is used
- `expires_at` is extended on activity
- expired sessions can be cleaned up through the agent service, which now also coordinates artifact cleanup for the same session
- if an expired `session_id` is reused later, the agent starts a fresh session state instead of loading stale history

### Skills

A skill is domain-specific guidance injected into the agent's prompt. Skills are not tools — they don't execute anything. They tell the agent *how* to approach a problem: what columns to use, how to define a metric, what patterns to follow.

Skills have:
- **Category** — connector, metric, workflow, domain, or compliance
- **Scope** — global (always active), connection-scoped (active when a specific connection is involved), or keyword-triggered
- **Instructions** — summary, recommended steps, dos/donts, output expectations

Examples: "Sample DB Schema Guide" (connector skill — tells the agent the table structure), "Customer Churn Analysis" (metric skill — defines how to calculate churn, triggered by keywords like "churn" or "retention"), and "Revenue Analysis" (metric skill — defines how to aggregate revenue from `orders.amount`).

### Workflows

A workflow is higher-level guidance that describes a multi-step analysis shape. Workflows are not tools and they do not execute by themselves. They help the agent plan a sequence of analysis steps for a class of requests.

Workflows have:
- **Triggers** — keyword and optional topic-profile matching
- **Steps** — ordered guidance with preferred tools or runtimes
- **Output expectations** — the kinds of artifacts or summaries the workflow should produce

Topic profiles can also carry explicit workflow allowlists. When present, the agent only resolves workflows whose ids are active for that user's topic context.

Examples: "Churn Investigation Workflow" (identify the customer base, compute churn by segment, optionally refine a prior churn artifact with Python) and "Revenue Breakdown Workflow" (aggregate revenue, break down by category or period, and rank results).

Workflows can also activate specific policies for execution-time enforcement. For example, the seeded revenue workflow activates a policy that denies `python_transform`, which keeps that workflow on a SQL-first path unless a different workflow explicitly permits later transformation behavior.

### Policies

A policy is a rule evaluated at execution time. Policies have a **type** (execution_routing, tool_selection, validation, security), a **scope** (global or linked to specific topic profiles), a **condition** (when to trigger), and an **effect** (what happens).

Conditions can check: source types, tool names, estimated row counts, max source table rows, and query patterns (has WHERE, has LIMIT). All conditions on a policy are AND’d — all must be met for the effect to apply.

Effects include: denying specific tools or runtimes, forcing deferred execution mode, requiring approval before running. Policies are evaluated by the Execution Service before any runtime is called — they can block or defer execution entirely.

Policies are prioritized. Higher-priority policies take precedence when effects conflict.

### Deferred Execution (Jobs)

When a policy forces deferred execution (e.g., a large unbounded query), the Execution Service creates a job record, launches the execution in the background, and returns a job ID immediately. The agent reports the deferral to the user, who can check status later via the `check_job_status` tool.

Job states: submitted → running → completed/failed. Jobs store the original execution request, result, logs, and error messages.

### Topic Profiles

A topic profile defines a scoped workspace: which tools, connections, runtimes, skills, workflows, and policies are available. Users are assigned to one or more topic profiles. When the agent receives a request with a `user_id`, it resolves the user's active profiles and restricts everything accordingly.

If no `user_id` is provided, the agent operates with full access (backward compatible).

Examples: "Finance Analysis" (SQL + inspect only, sample_db connection, no Python), "General Exploration" (all tools, all connections, all skills).

## Tech stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Web framework | FastAPI |
| LLM | Anthropic Claude (swappable) |
| Database | PostgreSQL 16 |
| Object storage | MinIO (S3-compatible) |
| Tabular format | Apache Parquet |
| Infrastructure | Docker Compose |

## Running it

```bash
make infra          # Start Postgres + MinIO
make install        # Install Python dependencies
make seed           # Create sample data + register connection + register runtimes

# In separate terminals:
make artifact       # Port 8002
make runtime-sql    # Port 8010
make runtime-python # Port 8011
make execution      # Port 8001
make agent          # Port 8000
```

## Testing

```bash
# Step 1: Topic-scoped user — finance user (SQL only, no Python)
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "fin-1", "user_id": "finance-user", "message": "Show me revenue by product category"}' \
  | python -m json.tool

# Step 2: Full-access user — analyst with all tools
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "analyst-1", "user_id": "analyst-user", "message": "Get all customers and filter to inactive ones"}' \
  | python -m json.tool
```

## What's next

See [app-specs/plan.md](app-specs/plan.md) for the full phased plan. The immediate next steps are:
- Workflow-aware runtime preferences beyond the current workflow policy activation path
