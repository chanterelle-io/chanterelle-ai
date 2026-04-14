# Analytics Agent App — Architecture Specification

## 1. Overview

The Analytics Agent App is a session-based analytical platform where a user interacts with an AI agent to retrieve information, analyze data, and generate outputs from connected sources, uploaded documents, and prior session results.

The system combines:

- Conversational reasoning
- Governed source access
- Reusable analytical artifacts
- Isolated execution runtimes
- Reusable skills that guide the agent in source-specific, domain-specific, and workflow-specific tasks
- Topic profiles that bundle capabilities and governance per use case
- Policies that constrain and enforce platform behavior

The core idea: the conversation is not just text. It is backed by a session workspace containing artifacts, runtime state, connection bindings, execution history, and active topic profiles.

---

## 2. Product Goal

Let users perform multi-step analytics naturally in conversation while preserving the structure, traceability, and safety of a real analytics platform.

A user should be able to:

- Ask for data from a connected source
- Save the result as a reusable table artifact
- Reuse that table in a later step
- Run Python, SQL, or distributed jobs on it
- Generate charts, summaries, or reports
- Inspect or export the results

The platform supports both interactive analysis and heavier asynchronous analytical workloads.

---

## 3. Design Principles

### 3.1 Session-scoped continuity

A session retains more than chat history. It includes reusable data artifacts, job history, runtime bindings, and execution context.

### 3.2 Runtime isolation

Execution-capable tools do not run inside the agent process. They run in isolated runtimes with controlled dependencies, credentials, and policies.

### 3.3 Artifacts as first-class objects

Important outputs — especially tables — are stored as reusable artifacts with schema, lineage, and retention metadata.

### 3.4 Storage and compute separation

Artifacts are persisted independently of any runtime. Runtimes may come and go; artifacts remain available through the session artifact store.

### 3.5 Skills above tools

Tools perform actions. Skills provide reusable know-how that helps the agent use tools correctly and consistently.

### 3.6 Policy-driven execution

The agent requests work, but the platform decides the runtime class, execution mode, and credential injection strategy according to policy.

### 3.7 Reproducibility and governance

The system preserves lineage, execution context, and source references for trust, debugging, and auditability.

### 3.8 Capability-bounded activation

The agent operates within the intersection of the user's allowed topic profiles and the inferred relevance of those profiles to the current request. Capabilities are dynamic but bounded.

---

## 4. Core Concepts

### 4.1 Agent

The agent is the orchestration and reasoning layer. It:

- Interprets user intent
- Resolves applicable topic profiles
- Activates relevant skills and policies
- Selects tools
- References artifacts
- Submits execution requests
- Composes the final user response

The agent does not directly execute arbitrary code.

### 4.2 Session

A session is the analytical workspace attached to a conversation. It contains:

- Conversation history
- Accessible connections
- Uploaded files and documents
- Session artifacts
- Pending and completed jobs
- Runtime instances or bindings
- Execution metadata
- Recent active topic profiles and activation history

A session does not have a single hard-coded topic. Topic activation is dynamic and request-driven, bounded by user permissions.

### 4.3 Artifact

An artifact is any persisted or referenceable output available to the session:

- Table
- File
- Chart
- Report
- Log
- Derived model output

Artifacts are runtime-independent and reusable across later steps.

**Contract:** see [contracts/artifact-contract.md](contracts/artifact-contract.md)

### 4.4 Connection

A connection is a governed binding to an external source or system. It defines:

- Endpoint parameters
- Authentication references
- Allowed operations
- Allowed runtime types
- Attached skills
- Governance and security policy

A connection does not own a runtime.

**Contract:** see [contracts/connection-contract.md](contracts/connection-contract.md)

### 4.5 Skill

A skill is a reusable unit of procedural knowledge that guides the agent for a class of tasks, sources, metrics, or workflows.

Skills apply at multiple scopes:

| Scope | Example |
|-------|---------|
| Global | "Always validate metric outputs before returning" |
| Workspace | "In this org, use reporting calendar for date alignment" |
| Domain | "For churn analysis, follow this methodology" |
| Connection | "This warehouse uses `dw.dim_date` for date joins" |
| Workflow | "Variance analysis requires current vs prior period comparison" |
| Session | "User prefers Python over SQL for transformations" |

Skills guide how to perform a class of tasks well. They suggest and recommend.

**Contract:** see [contracts/skill-contract.md](contracts/skill-contract.md)

### 4.6 Policy

A policy constrains or directs what the system is allowed, required, or preferred to do. Policies enforce.

Examples:

- If estimated rows > 50M, force deferred execution on a distributed runtime
- Do not use Python runtime with restricted source X
- Always run validation skill before returning regulated metrics
- Require approval before write operations
- Prefer warehouse pushdown over dataframe load when possible

Policies apply at scopes: global, workspace, domain, connection.

**Precedence rule:** policies override skill preferences. A skill may recommend Python, but a policy may require SQL pushdown first or prohibit Python on a restricted source.

**Contract:** see [contracts/policy-contract.md](contracts/policy-contract.md)

### 4.7 Workflow Definition

A workflow definition specifies a preferred multi-step pattern for certain intents. It is richer than a skill's `recommendedSteps` — it defines ordered steps, decision points, validations, and expected outputs.

Example: "Churn analysis workflow"
1. Retrieve customer cohort
2. Compute inactivity signals
3. Enrich with revenue
4. Segment by risk
5. Validate output columns
6. Return summary + table + chart

**Contract:** see [contracts/workflow-contract.md](contracts/workflow-contract.md)

### 4.8 Topic Profile

A topic profile is a capability and governance bundle that defines the tools, skills, workflows, policies, connections, and runtime types available when that topic is active.

Topic profiles are not hard-bound to sessions. Each user is granted access to a set of topic profiles, and the orchestration layer dynamically activates the relevant subset per request.

Examples:

| Topic | Enabled capabilities |
|-------|---------------------|
| Finance Analysis | SQL, Python, finance metric skills, finance validation policies |
| Document Reconciliation | Doc reading, table extraction, source querying, reconciliation workflows |
| Heavy Data Processing | Distributed runtime, async jobs, data engineering workflows, stricter execution routing |
| General Exploration | Broad tool set, lighter guardrails, generic analytics skills |

**Contract:** see [contracts/topic-contract.md](contracts/topic-contract.md)

### 4.9 Runtime Definition

A runtime definition is a template for an execution environment. It specifies image, installed dependencies, supported connection types, supported operations, resource profile, and isolation profile.

Drivers and connector libraries belong here (SQL Server ODBC, JDBC, Python data libraries, Spark connectors).

**Contract:** see [contracts/runtime-contract.md](contracts/runtime-contract.md)

### 4.10 Runtime Instance

A runtime instance is a live provisioned environment created or reused for a session or task. It may be created on demand, reused if compatible, and scoped to a session or task depending on policy.

**Contract:** see [contracts/runtime-contract.md](contracts/runtime-contract.md)

### 4.11 Execution Request

An execution request is the orchestration command sent by the agent to the execution layer. It specifies the tool and operation, target connection, input artifacts, requested runtime type, preferred execution mode, and expected outputs.

**Contract:** see [contracts/execution-request-contract.md](contracts/execution-request-contract.md)

### 4.12 Job

A job is the tracked record of an execution, especially important for deferred or long-running workloads.

---

## 5. High-Level Architecture

### Components Diagram

See [component-diagram.txt](component-diagram.txt)

### Subsystems

#### 5.1 Agent Orchestration Layer

- Interprets user requests
- Resolves topic profiles and intersects with user permissions
- Activates skills and policies from resolved scopes
- Selects tools
- Discovers and references artifacts
- Forms execution requests
- Summarizes results

#### 5.2 Session Manager

- Session lifecycle and state
- Artifact references
- Runtime bindings
- Job references
- Topic activation history

#### 5.3 Execution Manager

- Validates execution requests
- Enforces connection/runtime policy
- Selects runtime definitions
- Provisions or reuses runtime instances
- Decides sync vs async mode
- Injects credentials securely
- Collects and persists outputs

#### 5.4 Artifact Store and Catalog

- Persists artifacts in object storage
- Tracks schema, lineage, statistics, retention
- Provides previews and metadata inspection for agent and runtimes

#### 5.5 Connection Registry

- Stores connection definitions
- Auth references
- Policy metadata
- Attached skills
- Allowed runtime types

#### 5.6 Skill Registry

- Stores versioned skills at all scopes
- Trigger metadata
- Helper assets
- Validations

#### 5.7 Policy Registry

- Stores active policies at all scopes
- Condition/effect evaluation
- Priority ordering

#### 5.8 Workflow Registry

- Stores workflow definitions
- Trigger metadata
- Step definitions

#### 5.9 Topic Profile Registry

- Stores topic profiles
- User-topic assignments
- Override rules

#### 5.10 Job Manager

- Job records and status tracking
- Logs
- Retries where allowed
- Completion callbacks and artifact registration

#### 5.11 Runtime Registry and Provisioner

- Runtime definition catalog
- Runtime instance creation and reuse
- Session/task scoped binding

#### 5.12 Secret Manager

- Credential storage
- Just-in-time token/secret retrieval
- Ephemeral injection into runtimes

---

## 6. Storage Model

### 6.1 Canonical artifact storage

Object storage is the source of truth for session artifacts.

Artifacts may need to survive runtime restarts, be read by multiple runtime types, be reused across executions, participate in retention and lifecycle policies, and support async jobs and distributed execution.

### 6.2 Runtime-local storage

Each runtime may use a local filesystem for temporary scratch data, caches, and transient execution files. This is not the system of record.

> **Rule:** Object storage is the source of truth. Runtime-local filesystem is temporary execution scratch space.

---

## 7. Tabular Artifact Model

### 7.1 Default persisted format

Parquet. This provides columnar efficiency, compression, schema support, interoperability across runtimes, and efficient reuse.

> **Rule:** Tabular session artifacts are persisted in Parquet by default unless a tool contract explicitly requires another representation.

### 7.2 Alternative runtime-native representations

A persisted Parquet artifact may be projected into Pandas/Polars DataFrames, Arrow tables, temporary SQL views or temp tables, or distributed dataframes. These are execution representations, not the canonical stored form.

### 7.3 Managed table promotion

Default session artifact = Parquet in object storage. Optional promotion to managed table (Delta, Iceberg) when a dataset becomes repeatedly queried, incrementally updated, shared across sessions, part of a production workflow, or large enough to justify richer table semantics.

### 7.4 SQL over results

The system supports querying stored artifacts with SQL as a capability of compatible runtimes, not as the primary storage model. Artifact stored as Parquet → SQL runtime registers as temporary external table/view → agent queries with SQL.

---

## 8. Artifact Catalog and Schema Tracking

Each table artifact tracks:

- Identifier, name, type
- Storage pointer
- Schema (columns, logical types, primary key, partition columns, time column, semantic hints)
- Statistics (row count, column count, byte size, distinct counts, null counts)
- Lineage (source kind, source refs, parent artifacts, transformation summary, producing skills)
- Retention class
- Access policy
- Preview availability

This allows the agent to determine: whether a prior artifact is reusable, fits the requested calculation, is too large for an interactive runtime, or should be filtered/projected before loading.

---

## 9. Retention Model

Session workspaces are not infinite memory.

### 9.1 Retention classes

| Class | Behavior |
|-------|----------|
| `temporary` | Auto-evicted when unreferenced or on quota pressure |
| `reusable` | Kept longer, evicted when unpinned and under pressure |
| `pinned` | Never auto-evicted |
| `persistent` | Survives session end |

### 9.2 Eviction order

1. Temporary and unreferenced
2. Temporary lightly referenced
3. Reusable but unpinned
4. Never auto-evict pinned artifacts

> **Rule:** Retention is based on recency, size, and importance — not recency alone.

### 9.3 User involvement

When automatic cleanup is insufficient or ambiguous, the user should be asked which artifacts to keep, archive, or remove.

---

## 10. Execution Model

### 10.1 Interactive execution

Low-latency analysis, small to medium datasets, quick SQL queries, table filtering, chart generation, aggregation on available artifacts.

### 10.2 Deferred execution

Large-scale scans, long-running computations, wide date-range processing, distributed jobs, resource-heavy transformations, large joins, model scoring. Tracked as a job.

---

## 11. Execution Policy and Routing

Execution mode is not hardcoded from natural language. The platform uses an execution policy layer that routes workloads based on:

- Estimated row count and bytes scanned
- Expected duration
- Source type and operation complexity
- Allowed resource profile
- Sensitivity level
- Workspace quotas
- Runtime availability
- Cost policy
- Active policies from resolved topic profiles

> **Rule:** The agent chooses the tool and expresses the task intent. The execution manager chooses the runtime class and execution mode.

---

## 12. Topic Profile Resolution

When a new request arrives:

1. Get user's allowed topic profiles
2. Infer relevant topics from: request text, selected connections, requested outputs, prior artifacts
3. Intersect: relevant topics ∩ user-allowed topics
4. Activate corresponding: tools, skills, workflows, policies
5. Execute only within that resulting capability set

> **Rule:** The agent does not activate a topic profile unless the user is allowed that topic and policies permit it. Activation is dynamic but bounded.

Optional: `TurnTopicActivation` records can be stored for debugging, audit, and usage analytics.

---

## 13. Skill and Policy Resolution

When the orchestration layer plans a response, it resolves guidance in this order:

1. **Global policies** — platform-wide constraints
2. **Workspace policies** — organization-specific constraints
3. **Domain/workflow skills** — methodology and workflow guidance
4. **Connection-attached skills** — source-specific conventions and pitfalls
5. **Execution policies** — routing, mode, and resource decisions
6. Produce the execution plan within the intersection of all resolved constraints

### Precedence hierarchy

| Layer | Role |
|-------|------|
| Skills | Suggest and guide |
| Workflow definitions | Structure multi-step patterns |
| Policies | Constrain and enforce |

Policies override skill preferences. Workflow steps are subject to policy constraints.

---

## 14. Connection Model

A connection represents a governed source binding.

Contains:
- Source type, endpoint parameters
- Authentication references
- Allowed operations
- Allowed runtime types
- Attached skills
- Governance metadata

Does not contain:
- Runtime instances
- Runtime dependency installation logic
- Embedded raw credentials

> **Rule:** Connections define source access and policy. They do not contain drivers or own runtime instances.

---

## 15. Runtime Model

### 15.1 Runtime definitions

A runtime definition specifies: runtime type, image reference, dependency profile, supported connection types, supported operations, resource profile, isolation profile, execution mode support.

Drivers and connector libraries belong in runtime definitions (ODBC, JDBC, Python libraries, Spark connectors).

### 15.2 Runtime instances

A runtime instance is the actual provisioned environment. It may be created on demand, reused if compatible, session-scoped, or task-scoped depending on policy.

> **Rule:** Runtime images contain dependencies. Connection definitions contain source access metadata. Credentials are injected at execution time.

---

## 16. Credential Handling

Credentials are never embedded permanently in runtime images or exposed to the agent.

The platform:
- Stores auth references in the connection definition
- Fetches credentials or tokens just in time
- Injects them into the selected runtime for the required scope
- Never surfaces raw secrets to the model
- Discards or expires them after use

Injection scopes:
- **Ephemeral task-scoped** (recommended default)
- Session-scoped
- Restricted runtime-scoped

---

## 17. Lifecycle Flows

### 17.1 Interactive data retrieval

1. User asks for a dataset from a connection
2. Agent resolves topic profiles → activates skills and policies
3. Agent activates relevant connector skills
4. Agent builds an execution request for the appropriate tool
5. Execution manager resolves the target connection
6. Execution manager evaluates policies and selects a compatible runtime definition
7. Runtime instance is created or reused
8. Credentials are injected just in time
9. Tool executes
10. Output table is persisted as Parquet in object storage
11. Artifact is registered with schema, lineage, and preview
12. Agent responds with summary and preview

### 17.2 Reuse of prior artifact

1. User refers to a prior result naturally
2. Agent resolves the reference through the artifact catalog
3. Agent inspects artifact metadata (schema, size, lineage)
4. Agent decides whether to reuse directly, project a subset, or enrich with a new query
5. Execution request includes the artifact as an input
6. Runtime loads the artifact in native form
7. Derived outputs are registered as new artifacts with lineage

### 17.3 Deferred big-data execution

1. User requests a large or long-running analysis
2. Agent selects the relevant tool and intent
3. Execution policy classifies the workload as deferred
4. Execution manager selects a distributed or large-scale runtime
5. Job record is created
6. Runtime executes asynchronously
7. Logs and status are tracked in the job manager
8. On completion, outputs are stored as artifacts
9. Session state reflects completed job and reusable outputs

### 17.4 Topic-switching mid-session

1. User starts in Finance Analysis (SQL queries, metric skills)
2. User requests large-scale processing beyond interactive capacity
3. Orchestration infers Heavy Data Processing topic is relevant
4. System verifies user has access to that topic profile
5. Activates distributed runtime policies and data engineering workflows
6. Execution proceeds under the merged capability set

---

## 18. Example Scenario: Churn-Risk Analysis

1. User asks for customers who signed up in the last 6 months and their activity
   → SQL runtime retrieves the data → stores `customers_last_6_months`
2. User asks to keep only customers active initially but inactive in the last 30 days
   → Python runtime loads `customers_last_6_months`, filters → stores `potential_churn_customers`
3. User asks to enrich with revenue and number of purchases
   → SQL runtime uses customer IDs from the derived artifact → stores `churn_customers_enriched`
4. User asks to segment them by risk
   → Python runtime produces `churn_segments`
5. Agent returns high-risk high-value customers, charts, and optional exports

This demonstrates: artifact reuse, progressive refinement, cross-runtime interoperability, session continuity, and lineage across steps.

---

## 19. Core Contracts

| Contract | File |
|----------|------|
| Artifact | [contracts/artifact-contract.md](contracts/artifact-contract.md) |
| Skill | [contracts/skill-contract.md](contracts/skill-contract.md) |
| Connection | [contracts/connection-contract.md](contracts/connection-contract.md) |
| Runtime Definition & Instance | [contracts/runtime-contract.md](contracts/runtime-contract.md) |
| Execution Request | [contracts/execution-request-contract.md](contracts/execution-request-contract.md) |
| Policy | [contracts/policy-contract.md](contracts/policy-contract.md) |
| Workflow Definition | [contracts/workflow-contract.md](contracts/workflow-contract.md) |
| Topic Profile & User Assignment | [contracts/topic-contract.md](contracts/topic-contract.md) |

---

## 20. System Rules

1. Artifacts are runtime-independent session objects stored in the artifact store.
2. Tabular artifacts are persisted in Parquet by default.
3. Runtimes may project artifacts into native execution forms, but those are not the canonical persisted form.
4. Connections define source access and policy; they do not own runtimes.
5. Runtime definitions define execution environments and installed dependencies.
6. Credentials are injected just in time and are not exposed to the agent as raw values.
7. Skills are reusable knowledge objects that guide the agent; they are distinct from tools.
8. The agent chooses tools and intent; the execution manager chooses runtime class and execution mode.
9. Retention is based on recency, size, and importance, with support for pinning.
10. Deferred executions must be tracked as jobs and produce normal registered artifacts on completion.
11. Policies override skill preferences. Skills suggest; policies enforce.
12. The agent does not activate a topic profile unless the user is permitted and the request warrants it.

---

## 21. MVP Scope

### Include

- Object-storage-backed artifact store
- Parquet table persistence
- Artifact catalog with schema and lineage basics
- Connection registry
- One SQL runtime
- One Python runtime
- Synchronous interactive execution
- Basic deferred job support
- Connector skills and metric skills
- Workspace retention with temporary / reusable / pinned classes
- Lightweight policy registry (execution routing policies)
- Topic profiles with user assignment (at least 2 profiles)
- Skills with multi-scope resolution (global + connection)

### Defer

- Managed-table promotion (Delta/Iceberg)
- Rich governance and audit
- Workflow definitions as a separate registry (use skill `recommendedSteps` for MVP)
- Dynamic topic switching mid-session (start with per-session topic selection)
- Distributed big-data runtimes

---

## 22. Service Boundaries

See [services.md](services.md) for detailed service definitions.

Recommended production shape: **6 services**.

| Service | Owns |
|---------|------|
| **Agent Service** | Orchestration, session-aware planning, topic resolution, response composition |
| **Execution Service** | Execution request validation, policy evaluation, routing, credential binding, runtime invocation |
| **Artifact Service** | Artifact catalog, object storage reads/writes, previews, retention |
| **Connection Service** | Connection definitions, auth refs, connection policy |
| **Runtime Service** | Runtime definitions, provisioning, runtime instances |
| **Job Service** | Async job lifecycle, events, logs, completion callbacks |

For MVP, these can be merged into fewer deployables.

---

## 23. Final Architecture Statement

The Analytics Agent App is a session-based analytical platform in which an AI agent orchestrates data retrieval, document understanding, and analytical execution through tools. The agent operates within dynamically resolved topic profiles that bundle allowed tools, skills, policies, workflows, and connections per user and per request. Execution-capable tools run in isolated runtimes provisioned from predefined runtime definitions and authorized through connection policies. Session outputs are persisted as reusable artifacts, with Parquet as the default tabular storage format and schema, lineage, and retention metadata registered in an artifact catalog. The platform supports both interactive and deferred execution. Skills provide source-specific, domain-specific, and workflow-specific guidance, while policies constrain and enforce platform behavior. The result is a system where users can perform multi-step analytics naturally in conversation while the platform preserves structure, traceability, governance, and safety.