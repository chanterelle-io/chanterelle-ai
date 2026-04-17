# Chanterelle — System Overview

## What is Chanterelle?

Chanterelle is a session-based analytics platform where a user interacts with an AI agent to retrieve, analyze, and generate outputs from connected data sources. The user talks in natural language; the platform handles SQL execution, result storage, and multi-step analytical workflows behind the scenes.

## How it works

The user sends a message. The agent (powered by an LLM) interprets the request, writes a SQL query, and hands it off to the platform. The platform runs the query against the right data source, stores the result as a reusable artifact, and returns a summary to the user. On follow-up questions, the agent can reference prior artifacts — building analysis step by step.

```
User
  │
  ▼
Agent Service ──── "What do we have? What should I do?"
  │                    │                    │
  │              reads artifacts      reads connections
  │                    │                    │
  │              Artifact Service    Execution Service
  │                                        │
  │                                  picks runtime
  │                                  resolves connection
  │                                  injects credentials
  │                                        │
  │                                   SQL Runtime ──── Data Source
  │                                        │
  │                                  Parquet result
  │                                        │
  │                              stores in Artifact Service
  │                                        │
  ▼                                        ▼
User sees summary                  Artifact available
                                   for future steps
```

## The four services

### Agent Service (port 8000)

The brain. Receives user messages, talks to the LLM, decides which tools to use, and composes the response.

On each turn it:
1. Loads session context — what connections are available, what artifacts already exist
2. Builds a system prompt with that context
3. Sends the conversation to the LLM
4. If the LLM calls a tool (e.g. `query_sql_source`), the agent executes it by calling the Execution Service
5. Feeds the tool result back to the LLM
6. Returns the LLM's final response to the user

The LLM provider is abstracted — currently Claude, swappable to any provider by implementing the `LLMProvider` interface.

### Execution Service (port 8001)

The dispatcher. Sits between the agent and the runtimes. The agent never talks to runtimes directly.

When a tool call comes in, the execution service:
1. **Resolves the connection** — looks up the connection name in the registry (Postgres), gets the type, host, path, and config
2. **Picks the runtime** — matches the task to a compatible runtime (for now: SQL task → SQL runtime)
3. **Calls the runtime** — sends the query + connection config over HTTP
4. **Handles the output** — takes the Parquet bytes from the runtime, registers the artifact via the Artifact Service, returns the artifact ID

Later it will also evaluate execution policies (should this be async? does the user have permission?), inject credentials just-in-time, and create tracked jobs for long-running work.

It also owns the **connection registry** — the list of data sources the platform knows about (stored in Postgres).

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

This is the one component that **must** run as a separate process. The core design principle is that execution happens in isolated runtimes with controlled dependencies, not inside the agent.

## Key concepts

### Artifacts

An artifact is a saved result — typically a table (Parquet file) but could also be a chart, file, or report. Artifacts are:
- **Runtime-independent** — stored in object storage, not tied to any execution environment
- **Reusable** — the agent can reference them in later steps
- **Tracked** — schema, lineage, and statistics are recorded in the catalog

### Connections

A connection defines how to reach a data source: type (SQLite, PostgreSQL, etc.), endpoint config, and authentication references. Connections don't own runtimes — they just describe where data lives.

### Sessions

A session is the workspace for a conversation. It tracks: messages, artifacts produced, jobs running, and which connections are accessible. Currently in-memory; will move to Postgres in Phase 2.

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
make seed           # Create sample data + register connection

# In separate terminals:
make artifact       # Port 8002
make runtime-sql    # Port 8010
make execution      # Port 8001
make agent          # Port 8000
```

## Testing

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-1", "message": "How many customers do we have?"}' \
  | python -m json.tool
```

## What's next

See [app-specs/plan.md](app-specs/plan.md) for the full phased plan. The immediate next steps are:
- Persistent sessions (Postgres-backed)
- Python runtime for data transformation
- Artifact reuse across steps
- Skill registry for domain-specific agent guidance
