# Service Boundaries

The platform is organized into 6 logical services. For MVP, these can be merged into fewer deployable units.

---

## 1. Agent Service

The orchestration core. Owns the reasoning loop, session-aware planning, and response composition.

### Responsibilities

- Receive user turns via the Agent API / BFF
- Load session context (artifacts, connections, jobs, topic profiles)
- Resolve applicable topic profiles for the current user and request
- Activate skills and policies from resolved scopes (global → workspace → domain → connection)
- Resolve workflow definitions when the request matches a known workflow trigger
- Select tools and form execution requests
- Submit execution requests to the Execution Service
- Merge tool outputs into the final user response
- Persist turn-level topic activation records for audit

### Owns

- Agent Orchestration Layer
- Session Manager (session state, turn context, artifact references, runtime bindings, job references, topic activation history)
- Agent API / BFF endpoint

### Depends on

- Skill Registry (read)
- Policy Registry (read)
- Workflow Registry (read)
- Topic Profile Registry (read)
- Artifact Catalog (read)
- Execution Service (write — submit execution requests)
- Job Service (read — check job status)

---

## 2. Execution Service

The central control plane for execution. Translates execution requests into concrete runtime invocations under policy governance.

### Responsibilities

- Validate incoming execution requests
- Resolve target connections from the Connection Registry
- Evaluate execution policies (routing, mode, resource constraints)
- Select a compatible runtime definition
- Provision or reuse a runtime instance via the Runtime Service
- Bind credentials just-in-time from the Secret Manager
- Decide sync vs async execution mode
- For sync: invoke the runtime and collect output
- For async: create a job via the Job Service, then invoke the runtime
- Persist output artifacts to the Artifact Store
- Register artifact metadata in the Artifact Catalog

### Owns

- Execution Manager (request validation, policy routing, runtime selection, credential binding, sync/async decision, output capture)

### Depends on

- Connection Service (read — resolve connections, auth refs, allowed runtimes)
- Policy Registry (read — evaluate execution policies)
- Runtime Service (read/write — select definitions, provision instances)
- Secret Manager (read — fetch credentials)
- Artifact Service (write — persist outputs, register metadata)
- Job Service (write — create jobs for deferred execution)

---

## 3. Artifact Service

Owns all artifact lifecycle: storage, cataloging, schema tracking, lineage, retention, and previews.

### Responsibilities

- Write artifact payloads to object storage
- Read artifact payloads for runtimes and agent inspection
- Maintain the artifact catalog (metadata, schema, statistics, lineage)
- Generate and serve artifact previews (sample rows, text snippets)
- Apply retention policies (temporary, reusable, pinned, persistent)
- Execute eviction when workspace quotas are exceeded
- Support artifact pinning and unpinning by users
- Expose metadata queries for the agent (column inspection, row counts, source references)

### Owns

- Artifact Catalog (metadata index)
- Artifact Store (object storage backend)
- Retention Manager

### Depends on

- Object storage infrastructure (external)

---

## 4. Connection Service

Owns connection definitions, authentication references, and connection-level policies.

### Responsibilities

- CRUD for connection definitions
- Store and manage auth references (secret refs, not raw secrets)
- Enforce connection-level governance (classification, allowed users, allowed workspaces, network policy)
- Track attached skill IDs per connection
- Track allowed and denied runtime types per connection
- Provide connection resolution for the Execution Service

### Owns

- Connection Registry

### Depends on

- Secret Manager (reference management — does not fetch raw secrets itself, only stores refs)

---

## 5. Runtime Service

Owns runtime definition management and runtime instance provisioning.

### Responsibilities

- CRUD for runtime definitions (image, dependencies, supported connections, resource profile, isolation profile)
- Provision new runtime instances on demand
- Reuse compatible existing instances when possible
- Manage runtime instance lifecycle (starting, ready, busy, idle, stopping, stopped, error)
- Bind runtime instances to sessions or tasks per policy
- Report runtime health and availability to the Execution Service

### Owns

- Runtime Registry (runtime definitions)
- Runtime Pool / Provisioner (runtime instances)

### Depends on

- Container/VM infrastructure (external)
- Secret Manager (receives injected credentials from Execution Service at invocation time)

---

## 6. Job Service

Owns the lifecycle of deferred and asynchronous executions.

### Responsibilities

- Create job records when the Execution Service classifies a workload as deferred
- Track job status (submitted, running, failed, completed)
- Collect and store execution logs
- Handle retries where policy allows
- On completion: notify the Execution Service to persist artifacts and register metadata
- Fire completion callbacks / events to the Agent Service
- Expose job status to the Agent Service and Client App

### Owns

- Job Manager (job records, status, logs, retries, completion events)

### Depends on

- Execution Service (receives job creation requests; sends completion notifications)
- Artifact Service (write — register final artifacts on job completion)

---

## Supporting Components (not standalone services)

### Secret Manager

- Stores encrypted credentials
- Provides just-in-time retrieval for runtime injection
- Supports ephemeral (task-scoped), session-scoped, and runtime-scoped injection
- May be implemented as an external managed service (e.g., Vault, AWS Secrets Manager, Azure Key Vault)

### Skill Registry

- Stores versioned skills at all scopes (global, workspace, domain, connection, workflow, session)
- Trigger metadata and helper assets
- Typically co-located with the Agent Service or as a shared data store

### Policy Registry

- Stores active policies at all scopes
- Condition/effect evaluation
- Priority ordering
- Typically co-located with the Agent Service or Execution Service

### Workflow Registry

- Stores workflow definitions with triggers and steps
- Typically co-located with the Agent Service

### Topic Profile Registry

- Stores topic profiles and user-topic assignments
- Typically co-located with the Agent Service

---

## MVP Deployment Topology

For MVP, the 6 services can collapse into 2-3 deployables:

| Deployable | Contains |
|------------|----------|
| **Agent + Orchestration** | Agent Service, Skill/Policy/Workflow/Topic registries, Session Manager |
| **Execution + Runtime** | Execution Service, Runtime Service, Connection Service, Job Service |
| **Artifact Store** | Artifact Service + object storage interface |

This gives clean separation between reasoning (agent), execution (platform), and data (artifacts) while keeping operational overhead low.