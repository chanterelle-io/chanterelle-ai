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

On If a `user_id` is provided, resolves the user's **topic profiles** — which tools, connections, and skills they're allowed to use
3. Filters connections and fetches applicable skills (scoped by topic profile if active)
4. Builds a system prompt with connections, artifacts, skill instructions, and topic constraints
5. Sends the conversation to the LLM (only the tools allowed by the topic profile)
6. If the LLM calls a tool (e.g. `query_sql_source`, `transform_with_python`, or `inspect_artifact`), the agent executes it by calling the Execution Service or Artifact Service
7. Feeds the tool result back to the LLM (including policy denial messages if blocked)
8. Returns the LLM's final response to the user
9. If the LLM calls a tool (e.g. `query_sql_source`, `transform_with_python`, or `inspect_artifact`), the agent executes it by calling the Execution Service or Artifact Service
7. Feeds the tool result back to the LLM (including policy denial messages if blocked)
8. Returns the LLM's final response to the user
9. Persists the updated session (messages + artifact references) to Postgres

The LLM provider is abstracted — currently Claude, swappable to any provider by implementing the `LLMProvider` interface.

**Tools available:**
- `query_sql_source` — execute SQL against a connected data source
- `transform_with_python` — run Python code on existing artifacts (loaded as pandas DataFrames)
- `inspect_artifact` — read sample rows and column details from an existing artifact without re-querying

### Execution Service (port 8001)

The dispatcher. Sits between the agent and the runtimes. The agent never talks to runtimes directly.

When a tool call comes in, the execution service:
1. **Resolves the connection** (for SQL) — looks up the connection name in the registry (Postgres), gets the type, host, path, and config
2. **Picks the runtime** — matches the tool to a runtime type via the runtime registry (e.g. `query_sql` → sql runtime, `python_transform` → python runtime)
3. **Loads input artifacts** (for Python transforms) — downloads Parquet from Artifact Service and base64-encodes for the runtime
4. **Calls the runtime** — sends the request over HTTP**skill registry**, **policy registry**, and **topic profile registry** — all stored in Postgres.

Before executing, it evaluates **policies** against the request context (tool, connection type, user's topic profiles). Policies can deny tools, deny runtimes, force deferred execution, or require approval. If a policy blocks the request, the execution service returns a `denied` status instead of running anything
5. **Handles the output** — takes the Parquet bytes from the runtime, registers the artifact via the Artifact Service (with lineage — source connection or parent artifacts), returns the artifact ID

It owns the **connection registry**, **runtime registry**, **skill registry**, **policy registry**, and **topic profile registry** — all stored in Postgres.

Before executing, it evaluates **policies** against the request context (tool, connection type, user's topic profiles). Policies can deny tools, deny runtimes, force deferred execution, or require approval. If a policy blocks the request, the execution service returns a `denied` status instead of running anything.

### Artifact Service (port 8002)

The data librarian. Owns two things:

- **Catalog** (Postgres) — metadata about every artifact: name, schema (columns + types), row count, byte size, lineage (which connection, what query produced it), retention class
- **Store** (MinIO/S3) — the actual Parquet files

When a query produces a table:
1. A catalog record is created with all metadata
2. The Parquet file is uploaded to object storage
3. The artifact is now available for future steps — the agent can inspect its schema, a Python runtime can load it, or the user can download it

It answers questions like: "What artifacts exist?", "What columns does `customers_last_month` have?", "Give me the Parquet bytes."

### SQL Runtime (port 8010)

The worker. Receives a SQL query + connection config, executes it against the actual data source, and returns the result as Parquet bytes.

Currently supports SQLite and PostgreSQL. The runtime is stateless — it doesn't store results or track sessions. It just runs queries and returns data.

### Python Runtime (port 8011)

The transformer. Receives Python code + input artifacts (as base64-encoded Parquet), loads them as pandas DataFrames, executes the code, and returns the result as Parquet bytes.

Used when the agent needs to filter, aggregate, or transform data from a previous step. The code must assign the output to a `result` variable (a DataFrame). Runs with restricted builtins for safety.

Like the SQL runtime, this is stateless and isolated.

## Key concepts

### Artifacts

An artifact is a saved result — typically a table (Parquet file) but could also be a chart, file, or report. Artifacts are:
- **Runtime-independent** — stored in object storage, not tied to any execution environment
- **Reusable** — the agent can reference them in later steps
- **Tracked** — schema, lineage, and statistics are recorded in the catalog

### Connections

A connection defines how to reach a data source: type (SQLite, PostgreSQL, etc.), endpoint config, and authentication references. Connections don't own runtimes — they just describe where data lives. Credentials are stored as references (e.g. `env:VAR_NAME`) and resolved at execution time — never exposed to the agent or stored in plaintext.

### Sessions

A session is the workspace for a conversation. It tracks: messages, artifacts produced, and which connections are accessible. Persisted in Postgres (messages and artifact references stored as JSONB). Sessions survive service restarts.

### Skills

A skill is domain-specific guidance injected into the agent's prompt. Skills are not tools — they don't execute anything. They tell the agent *how* to approach a problem: what columns to use, how to define a metric, what patterns to follow.

Skills have:
- **Category** — connector, metric, workflow, domain, or compliance
- # Policies

A policy is a rule evaluated at execution time. Policies have a **type** (execution_routing, tool_selection, validation, security), a **scope** (global or linked to specific topic profiles), a **condition** (when to trigger), and an **effect** (what happens).

Effects include: denying specific tools or runtimes, forcing deferred execution mode, requiring approval before running. Policies are evaluated by the Execution Service before any runtime is called — they can block execution entirely.

Policies are prioritized. Higher-priority policies take precedence when effects conflict.

### Topic Profiles

A topic profile defines a scoped workspace: which tools, connections, runtimes, skills, and policies are available. Users are assigned to one or more topic profiles. When the agent receives a request with a `user_id`, it resolves the user's active profiles and restricts everything accordingly.

If no `user_id` is provided, the agent operates with full access (backward compatible).

Examples: "Finance Analysis" (SQL + inspect only, sample_db connection, no Python), "General Exploration" (all tools, all connections, all skills).

##**Scope** — global (always active), connection-scoped (active when a specific connection is involved), or keyword-triggered
- **Instructions** — summary, recommended steps, dos/donts, output expectations

Examples: "Sample DB Schema Guide" (connector skill — tells the agent the table structure), "Customer Churn Analysis" (metric skill — defines how to calculate churn, triggered by keywords like "churn" or "retention").

### Policies

A policy is a rule evaluated at execution time. Policies have a **type** (execution_routing, tool_selection, validation, security), a **scope** (global or linked to specific topic profiles), a **condition** (when to trigger), and an **effect** (what happens).

Effects include: denying specific tools or runtimes, forcing deferred execution mode, requiring approval before running. Policies are evaluated by the Execution Service before any runtime is called — they can block execution entirely.

Policies are prioritized. Higher-priority policies take precedence when effects conflict.

### Topic Profiles

A topic profile defines a scoped workspace: which tools, connections, runtimes, skills, and policies are available. Users are assigned to one or more topic profiles. When the agent receives a request with a `user_id`, it resolves the user's active profiles and restricts everything accordingly.

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
# Step 1: Query data
curl -s http://localhost:8000/chat \

# Step 5: Topic-scoped user — finance user (SQL only, no Python)
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "fin-1", "user_id": "finance-user", "message": "Show me revenue by product category"}' \
  | python -m json.tool

# Step 6: Full-access user — analyst with all tools
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "analyst-1", "user_id": "analyst-user", "message": "Get all customers and filter to inactive ones"}' \
  | python -m json.tool
```

## What's next

See [app-specs/plan.md](app-specs/plan.md) for the full phased plan. The immediate next steps are:
- Deferred execution / job manager
- Retention + artifact previews
- Workflow definitions + advanced skill

# Step 3: Skill-guided analysis (churn skill activates on keyword)
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-2", "message": "what is the customer churn?"}' \
  | python -m json.tool

# Step 4: Inspect artifact data (no new query, reads existing artifact)
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-2", "message": "show me the actual rows"}' \
  | python -m json.tool

# Step 5: Topic-scoped user — finance user (SQL only, no Python)
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "fin-1", "user_id": "finance-user", "message": "Show me revenue by product category"}' \
  | python -m json.tool

# Step 6: Full-access user — analyst with all tools
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "analyst-1", "user_id": "analyst-user", "message": "Get all customers and filter to inactive ones"}' \
  | python -m json.tool
```

## What's next

See [app-specs/plan.md](app-specs/plan.md) for the full phased plan. The immediate next steps are:
- Deferred execution / job manager
- Retention + artifact previews
- Workflow definitions + advanced skills
