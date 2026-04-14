Analytics Agent App — System Design Specification
1. Overview

The Analytics Agent App is a session-based analytical workspace where a user interacts with an AI agent to retrieve information, analyze data, and generate outputs from connected sources, uploaded documents, and prior session results.

The system combines:

conversational reasoning,
governed source access,
reusable analytical artifacts,
isolated execution runtimes,
and reusable skills that guide the agent in how to perform source-specific, domain-specific, and workflow-specific tasks.

The core idea is that the conversation is not just text. It is backed by a session workspace containing artifacts, runtime state, connection bindings, and execution history.

2. Product goal

The goal of the app is to let users perform multi-step analytics naturally in conversation while preserving the structure, traceability, and safety of a real analytics platform.

A user should be able to:

ask for data from a connected source,
save the result as a table artifact,
reuse that table in a later step,
run Python or SQL or distributed jobs on it,
generate charts, summaries, or reports,
and inspect or export the results.

The platform should support both:

interactive analysis,
and heavier asynchronous analytical workloads.
3. Design principles
3.1 Session-scoped continuity

A session retains more than chat history. It includes reusable data artifacts, job history, runtime bindings, and execution context.

3.2 Runtime isolation

Execution-capable tools do not run inside the agent process. They run in isolated runtimes with controlled dependencies, credentials, and policies.

3.3 Artifacts as first-class objects

Important outputs, especially tables, are stored as reusable artifacts with schema, lineage, and retention metadata.

3.4 Storage and compute separation

Artifacts are persisted independently of any runtime. Runtimes may come and go; artifacts remain available through the session artifact store.

3.5 Skills above tools

Tools perform actions. Skills provide reusable know-how that helps the agent use tools correctly and consistently.

3.6 Policy-driven execution

The agent requests work, but the platform decides the runtime class, execution mode, and credential injection strategy according to policy.

3.7 Reproducibility and governance

The system should preserve lineage, execution context, and source references for trust, debugging, and auditability.

4. Core concepts
4.1 Agent

The agent is the orchestration and reasoning layer. It:

interprets user intent,
selects tools,
activates relevant skills,
references artifacts,
submits execution requests,
and composes the final user response.

The agent does not directly execute arbitrary code.

4.2 Session

A session is the analytical workspace attached to a conversation. It contains:

conversation history,
accessible connections,
uploaded files and documents,
session artifacts,
pending and completed jobs,
runtime instances or bindings,
execution metadata.
4.3 Artifact

An artifact is any persisted or referenceable output available to the session, such as:

a table,
a file,
a chart,
a report,
a log,
derived model output.

Artifacts are runtime-independent and reusable across later steps.

4.4 Connection

A connection is a governed binding to an external source or system. It defines:

endpoint parameters,
authentication references,
allowed operations,
allowed runtime types,
attached skills,
governance and security policy.

A connection does not own a runtime.

4.5 Skill

A skill is a reusable unit of procedural knowledge that guides the agent for a class of tasks, sources, metrics, or workflows.

Examples:

how to query a SQL Server finance warehouse,
how to calculate net revenue,
how to perform churn analysis,
how to validate a metric before returning it.
4.6 Runtime Definition

A runtime definition is a template for an execution environment. It specifies:

image,
installed dependencies,
supported connection types,
supported operations,
resource profile,
isolation profile.
4.7 Runtime Instance

A runtime instance is a live provisioned environment created or reused for a session or task.

4.8 Execution Request

An execution request is the orchestration command sent by the agent to the execution layer. It specifies:

the tool and operation,
target connection or source,
input artifacts,
requested runtime type if any,
preferred execution mode,
expected outputs.
4.9 Job

A job is the tracked record of an execution, especially important for deferred or long-running workloads.

5. High-level architecture

The platform consists of the following major subsystems:

5.1 Agent orchestration layer

Responsible for:

interpreting user requests,
selecting tools,
discovering artifacts,
activating skills,
forming execution requests,
summarizing results.
5.2 Session manager

Responsible for:

session lifecycle,
session state,
artifact registry,
runtime bindings,
job registry.
5.3 Execution manager

Responsible for:

validating execution requests,
resolving connections,
selecting runtime definitions,
provisioning or reusing runtime instances,
deciding sync vs async mode,
injecting credentials securely,
collecting outputs.
5.4 Artifact store and catalog

Responsible for:

persisting artifacts,
schema tracking,
lineage,
retention,
previews,
metadata inspection by the agent and runtimes.
5.5 Connection registry

Responsible for:

storing connection definitions,
auth references,
policy metadata,
attached skills,
allowed runtime types.
5.6 Skill registry

Responsible for:

storing versioned skills,
scopes and triggers,
helper assets,
validations.
5.7 Job manager

Responsible for:

job records,
status tracking,
logs,
retries where allowed,
final artifact registration.
6. Storage model
6.1 Canonical artifact storage

The canonical persisted storage for session artifacts should be object storage.

This is recommended because artifacts may need to:

survive runtime restarts,
be read by multiple runtime types,
be reused across executions,
participate in retention and lifecycle policies,
support async jobs and distributed execution.
6.2 Runtime-local storage

Each runtime may use a local filesystem for temporary scratch data, caches, intermediate unpacking, and transient execution files.

This local storage is not the system of record.

Rule
Object storage is the source of truth
Runtime-local filesystem is temporary execution scratch space
7. Tabular artifact model
7.1 Default persisted format

The canonical persisted format for tabular artifacts is Parquet.

This provides:

columnar efficiency,
compression,
schema support,
interoperability across runtimes,
efficient reuse.
Rule

Tabular session artifacts are persisted in Parquet by default unless a tool contract explicitly requires another representation.

7.2 Alternative runtime-native representations

A persisted Parquet artifact may be projected into:

Pandas or Polars DataFrames,
Arrow tables,
temporary SQL views or temp tables,
distributed dataframes in a big-data runtime.

These are execution representations, not the canonical stored form.

7.3 Managed table promotion

Not every session table should be a managed Delta or Iceberg table by default.

Instead:

default session artifact = Parquet in object storage,
optional promotion to managed table abstraction when needed.

Promotion may be appropriate when a dataset becomes:

repeatedly queried,
incrementally updated,
shared across sessions,
part of a production workflow,
large enough to justify richer table semantics.
7.4 SQL over results

The system should support querying stored artifacts with SQL when useful.

This should be implemented as a capability of compatible runtimes, not as the primary storage model.

Example:

artifact stored as Parquet,
SQL runtime registers it as a temporary external table or view,
agent can query it with SQL.
8. Artifact catalog and schema tracking

The artifact catalog is required so the agent and runtimes can reason about prior outputs without reopening the full payload.

Each table artifact should track:

identifier,
name,
type,
storage pointer,
schema,
statistics,
lineage,
retention class,
access policy,
preview availability.

The agent should be able to inspect metadata such as:

columns,
logical types,
row counts,
time column,
source references,
producing tool,
parent artifacts.

This allows the agent to determine:

whether a prior artifact is reusable,
whether it fits the requested calculation,
whether it is too large for an interactive runtime,
whether it should be filtered or projected before loading.
9. Retention model

Session workspaces must not be treated as infinite memory.

The platform should apply:

workspace quotas,
artifact retention classes,
eviction rules,
optional user pinning.
9.1 Retention classes

Recommended retention classes:

temporary
reusable
pinned
persistent
9.2 Eviction order

Automatic eviction should consider:

importance,
recency,
size,
user pinning,
dependency relevance.

Recommended order:

temporary and unreferenced,
temporary lightly referenced,
reusable but unpinned,
never auto-evict pinned artifacts.
Rule

Retention should be based on recency, size, and importance, not recency alone.

9.3 User involvement

When automatic cleanup is insufficient or ambiguous, the user should be asked which artifacts to keep, archive, or remove.

10. Execution model

The platform should support two primary execution modes:

10.1 Interactive execution

Used for:

low-latency analysis,
small to medium datasets,
quick SQL queries,
table filtering,
chart generation,
aggregation on already available artifacts.
10.2 Deferred execution

Used for:

large-scale scans,
long-running computations,
wide date-range processing,
distributed jobs,
resource-heavy transformations,
large joins or model scoring jobs.

Deferred execution should be tracked as a job.

11. Execution policy and routing

Execution mode should not be hardcoded from natural language alone, such as “long period = async.”

Instead, the platform should use an execution policy layer that routes workloads according to estimated scale and constraints.

Factors may include:

estimated row count,
estimated bytes scanned,
expected duration,
source type,
operation complexity,
allowed resource profile,
sensitivity level,
workspace quotas,
runtime availability,
cost policy.
Rule

The agent chooses the tool and expresses the task intent.
The execution manager chooses the runtime class and execution mode.

12. Skills model

Skills are reusable knowledge assets that guide the agent.

12.1 What a skill is

A skill is not a tool. A skill tells the agent how to do something well.

Examples:

source conventions,
safe joins,
metric definitions,
domain-specific logic,
workflow steps,
validation rules.
12.2 Skill classes

Recommended classes:

connector
metric
workflow
domain
compliance
12.3 Skill content

A skill may contain:

instructions in markdown or structured text,
structured metadata,
optional helper assets,
validations,
output expectations.
12.4 Skill activation

Skills should be activated dynamically based on:

source type,
connection,
task type,
keywords,
domain.

Not all skills should be loaded all the time.

12.5 Connector skills

Attached to a source or connection, encoding:

schema conventions,
preferred paths,
safe defaults,
pitfalls,
source-specific examples.
12.6 Metric/workflow skills

Attached to common analyses such as:

revenue calculation,
churn analysis,
cohort logic,
compliance checks.
13. Connection model

A connection represents a governed source binding.

A connection should contain:

source type,
endpoint parameters,
authentication references,
allowed operations,
allowed runtime types,
attached skills,
governance metadata.

It should not contain:

runtime instances,
runtime dependency installation logic,
embedded raw credentials.
Rule

Connections define source access and policy.
They do not contain drivers or own runtime instances.

14. Runtime model
14.1 Runtime definition

A runtime definition specifies:

runtime type,
image reference,
dependency profile,
supported connection types,
supported operations,
resource profile,
isolation profile,
execution mode support.

Drivers and connector libraries belong here.

Examples:

SQL Server ODBC driver,
JDBC drivers,
Python data libraries,
Spark connector packages.
14.2 Runtime instance

A runtime instance is the actual provisioned environment.

It may be:

created on demand,
reused if compatible,
session-scoped,
or task-scoped depending on policy.
Rule

Runtime images contain dependencies.
Connection definitions contain source access metadata.
Credentials are injected at execution time.

15. Credential handling

Credentials must not be embedded permanently in runtime images or exposed to the agent.

The platform should:

store auth references in the connection definition,
fetch credentials or tokens just in time,
inject them into the selected runtime for the required scope,
avoid surfacing raw secrets to the model,
discard or allow them to expire after use.

Possible credential injection scopes:

ephemeral task-scoped,
session-scoped,
restricted runtime-scoped.

Recommended default:

ephemeral or just-in-time injection
16. Core contracts
16.1 Artifact contract
see contracts/artifact-contract.md
16.2 Skill contract
see contracts/skill-contract.md
16.3 Connection contract
see contracts/connection-contract.md
16.4 Runtime Definition and Runtime Instance contracts
see contracts/runtime-contract.md
16.5 Execution request contract
see contracts/execution-request-contract.md

17. Lifecycle flows
17.1 Interactive data retrieval flow
User asks for a dataset from a connection.
Agent activates relevant connector skills.
Agent builds an execution request for the appropriate tool.
Execution manager resolves the target connection.
Execution manager selects a compatible runtime definition.
Runtime instance is created or reused.
Credentials are injected just in time.
Tool executes.
Output table is persisted as Parquet in object storage.
Artifact is registered with schema, lineage, and preview.
Agent responds with summary and preview.
17.2 Reuse of prior artifact flow
User refers to a prior result naturally.
Agent resolves the reference through the artifact catalog.
Agent inspects artifact metadata.
Agent decides whether to:
reuse directly,
project a subset,
or enrich with a new query.
Execution request includes the artifact as an input.
Runtime loads the artifact in native form.
Derived outputs are registered as new artifacts.
17.3 Deferred big-data execution flow
User requests a large or long-running analysis.
Agent selects the relevant tool and intent.
Execution policy classifies the workload as deferred.
Execution manager selects a distributed or large-scale runtime.
Job record is created.
Runtime executes asynchronously.
Logs and status are tracked in the job manager.
On completion, outputs are stored as artifacts.
Session state reflects completed job and reusable outputs.
18. Example scenario
Scenario: churn-risk analysis
User asks for customers who signed up in the last 6 months and their activity.
SQL runtime retrieves the data and stores customers_last_6_months.
User asks to keep only customers active initially but inactive in the last 30 days.
Python runtime loads customers_last_6_months, filters it, and stores potential_churn_customers.
User asks to enrich with revenue and number of purchases.
SQL runtime uses the customer IDs from the derived artifact to query transactions and stores churn_customers_enriched.
User asks to segment them by risk.
Python runtime produces churn_segments.
Agent returns high-risk high-value customers, charts, and optional exports.

This scenario demonstrates:

artifact reuse,
progressive refinement,
cross-runtime interoperability,
session continuity,
and lineage across steps.
19. System rules

These are the rules I would explicitly keep in the spec.

Rule 1

Artifacts are runtime-independent session objects stored in the artifact store.

Rule 2

Tabular artifacts are persisted in Parquet by default.

Rule 3

Runtimes may project artifacts into native execution forms, but those are not the canonical persisted form.

Rule 4

Connections define source access and policy; they do not own runtimes.

Rule 5

Runtime definitions define execution environments and installed dependencies.

Rule 6

Credentials are injected just in time and are not exposed to the agent as raw values.

Rule 7

Skills are reusable knowledge objects that guide the agent; they are distinct from tools.

Rule 8

The agent chooses tools and intent; the execution manager chooses runtime class and execution mode.

Rule 9

Retention is based on recency, size, and importance, with support for pinning.

Rule 10

Deferred executions must be tracked as jobs and produce normal registered artifacts on completion.

20. MVP recommendation

A practical first version should not implement every feature at once.

MVP scope
object-storage-backed artifact store,
Parquet table persistence,
artifact catalog with schema and lineage basics,
connection registry,
one SQL runtime,
one Python runtime,
synchronous interactive execution,
basic deferred job support,
connector skills and metric skills,
workspace retention with temporary/reusable/pinned classes.
Managed-table promotion

This can wait until later.

Rich governance

Can start minimal and expand.

21. Final architecture statement

The Analytics Agent App is a session-based analytical platform in which an AI agent orchestrates data retrieval, document understanding, and analytical execution through tools. Execution-capable tools run in isolated runtimes provisioned from predefined runtime definitions and authorized through connection policies. Session outputs are persisted as reusable artifacts, with Parquet as the default tabular storage format and schema, lineage, and retention metadata registered in an artifact catalog. The platform supports both interactive and deferred execution, while reusable skills provide source-specific, domain-specific, and workflow-specific guidance to help the agent perform analyses consistently and safely.


22. Components Diagram
see components-diagram.txt

23. Core request flows
23.1 Interactive query flow
User → Client App → Agent API → Agent Orchestration
     → Skill Registry + Artifact Catalog + Session Manager
     → Execution Manager
     → Connection Registry + Runtime Registry + Secret Manager
     → SQL Runtime
     → Source DB
     → Artifact Store + Artifact Catalog
     → Agent Orchestration
     → Client App
23.2 Artifact reuse in Python flow
User asks follow-up
→ Agent resolves prior artifact from Artifact Catalog
→ Execution Manager selects Python Runtime
→ Python Runtime loads artifact from Artifact Store
→ output written back to Artifact Store
→ metadata registered in Artifact Catalog
→ response returned
23.3 Deferred big-data flow
User asks large computation
→ Agent submits Execution Request
→ Execution Manager classifies as deferred
→ Job Manager creates job
→ Runtime Provisioner starts Big Data Runtime
→ runtime executes
→ logs/status update Job Manager
→ final artifacts stored and registered
→ session updated
→ user sees job completion and outputs
Recommended service boundaries

A good first production shape is 6 services.

1. Agent Service

Owns:

orchestration
session-aware planning
response composition
2. Execution Service

Owns:

execution request validation
routing
credential binding
runtime invocation
3. Artifact Service

Owns:

artifact catalog
object storage writes/reads
previews
retention
4. Connection Service

Owns:

connection definitions
auth refs
connection policy
5. Runtime Service

Owns:

runtime definitions
runtime provisioning
runtime instances
6. Job Service

Owns:

async job lifecycle
events
logs
completion callbacks

For an MVP, these can be merged into fewer deployables.

# Changes
- adding one more layer above connection-level and task-level skills:
global skills
global policies
optionally workflow definitions

Right now, your design already supports:

connection-attached skills,
task/domain skills,
execution policy.

That is enough to start. But for cases like:

“when the user asks about X, follow this workflow”

you want a broader concept than just a connector skill.

The short answer

Your architecture can support this well if you treat skills/policies as applying at multiple scopes, not only at the connection level.

A good scope hierarchy is:

global
workspace / organization
domain
connection
session
task / workflow

That is the missing explicit refinement.

1. What you want is not just a connection skill

A connection skill is for things like:

how to query this source,
which date column to use,
which joins are safe,
source-specific pitfalls.

But:

“when asked about churn, do workflow A”

is broader.
That is more like a workflow skill or workflow policy.

So yes, the architecture supports it, but you should not model everything as “attached to connection.”

2. Recommended distinction

I would make this distinction very clearly.

Skills

Skills guide how to perform a class of tasks well.

Examples:

revenue calculation skill
churn analysis skill
finance SQL source skill
anomaly investigation skill
Policies

Policies constrain or direct what the system is allowed, required, or preferred to do.

Examples:

if estimated rows > threshold, use deferred execution
do not use Python runtime with restricted source X
always run validation skill before returning regulated metrics
require approval before write operations
prefer warehouse pushdown over dataframe load when possible
Workflow definitions

Workflow definitions specify a preferred multi-step pattern for certain intents.

Examples:

“customer churn workflow”
“financial variance analysis workflow”
“document + source reconciliation workflow”

That third concept is extremely useful for what you are describing.
Yes, your current architecture can host overall skills/policies

It already has the right ingredients:

a Skill Registry
an Execution Manager
a Connection Registry
session-aware orchestration
policy-based execution routing

That means you can extend skill resolution beyond source-specific skills.

The main thing to add is:

the agent orchestration layer should resolve applicable skills and policies from multiple scopes before planning or executing.

Best way to model it

I recommend explicitly expanding SkillScope and introducing a Policy object.

Expanded skill scope

Your skills should be able to apply at:

global level
workspace level
domain level
source/connection level
workflow/task level

For example:

interface SkillScope {
  level?: "global" | "workspace" | "domain" | "connection" | "workflow" | "session";
  sourceTypes?: string[];
  connectionIds?: string[];
  runtimeTypes?: string[];
  toolNames?: string[];
  taskTypes?: string[];
  domains?: string[];
  workspaceIds?: string[];
}

That way you can define:

a global workflow skill,
a workspace-specific compliance skill,
a connection-specific SQL skill.
5. Add a Policy contract

I would add a separate policy object like this:

type PolicyType =
  | "execution_routing"
  | "tool_selection"
  | "validation"
  | "security"
  | "workflow_preference"
  | "response_requirement";

interface Policy {
  id: string;
  name: string;
  type: PolicyType;
  status: "active" | "disabled" | "deprecated";

  scope: {
    level?: "global" | "workspace" | "domain" | "connection";
    workspaceIds?: string[];
    connectionIds?: string[];
    taskTypes?: string[];
    domains?: string[];
  };

  condition: Record<string, unknown>;
  effect: Record<string, unknown>;

  priority?: number;
  description?: string;
}
Example policy

“If user asks about revenue, always apply revenue validation before returning answer.”

Condition:

{
  "taskType": "revenue_analysis"
}

Effect:

{
  "requiredSkillIds": ["skill_revenue_validation_v1"]
}

Another:
“If estimated rows > 50 million, force deferred big-data runtime.”

Effect:

{
  "forceExecutionMode": "deferred",
  "preferredRuntimeType": "spark-runtime"
}
6. Workflow definitions are especially useful

For your example, I think a dedicated workflow definition concept is actually better than overloading normal skills.

Because “do this workflow when asked about X” implies:

ordered steps,
decision points,
validations,
maybe fallback behavior,
expected outputs.

That is more than plain guidance.

Example workflow definition
interface WorkflowDefinition {
  id: string;
  name: string;
  version: string;
  status: "active" | "disabled";

  triggers: {
    taskTypes?: string[];
    keywords?: string[];
    domains?: string[];
  };

  steps: WorkflowStep[];
  requiredSkillIds?: string[];
  outputExpectations?: string[];
}

interface WorkflowStep {
  stepId: string;
  title: string;
  description: string;
  preferredTool?: string;
  preferredRuntimeType?: string;
  validationRules?: string[];
}
Example

“Churn analysis workflow”

retrieve customer cohort
compute inactivity signals
enrich with revenue
segment by risk
validate output columns
return summary + table + chart

This fits your architecture very naturally.

7. Recommended resolution order

In the orchestration layer, when a new user request comes in, I would have the agent resolve guidance in this order:

global policies
workspace policies
domain/workflow skills
connection-attached skills
execution policies
then produce the execution plan

So if a user asks:

“Analyze churn risk for our latest customers”

the system could automatically resolve:

global churn workflow
workspace-specific customer data policy
connection-specific warehouse skill
execution routing policy

That is exactly the kind of intelligence you want.

8. Very important: policies should override preferences

A useful rule is:

skills suggest and guide
workflow definitions structure
policies constrain and enforce

So:

a skill may recommend Python,
but a policy may require SQL pushdown first,
or prohibit Python on a restricted source.

That separation keeps governance clean.

9. Practical examples
Example A: global workflow skill

“When asked for variance analysis, compare current vs prior period, calculate delta, rank top drivers, then return summary plus table.”

This is a workflow skill or workflow definition with scope global or workspace.

Example B: global response policy

“For finance metrics, include methodology note and validation check.”

This is a policy.

Example C: connection-specific rule

“When using finance warehouse, always filter to approved reporting calendar table.”

This is a connector skill or connection-scoped policy.

Example D: execution policy

“If row estimate exceeds threshold, switch to deferred runtime.”

This is an execution policy.

10. My recommendation

Yes, your architecture allows this, but I would explicitly add:

policy registry
workflow definition registry or treat workflow definitions as a special skill subtype
multi-scope skill resolution

If you want to keep it simpler for MVP, you can avoid a separate workflow object and do this instead:

MVP version

Use skills with:

category = workflow
scope.level = global | workspace | domain | connection
instructions.recommendedSteps
optional validations

And add a separate lightweight policies table for enforcement rules.

That is probably the best first version.

# Topics
I would strongly prefer topics/profiles/capabilities bundles over fully separate agents for your kind of app, at least at first.

My recommendation

Start with:

one core agent
multiple topic profiles
each profile activates a set of:
tools
skills
policies
workflow definitions
maybe UI defaults

That is usually better than creating many truly separate agents.

Good mental model

Think of it like this:

Agent = reasoning engine
Topic/Profile = configuration pack
Skills = reusable know-how
Tools = capabilities
Policies = constraints
Workflows = recommended multi-step plans

That separation scales very well.

When separate agents do make sense

Separate agents can be justified when there is a real boundary in one of these areas:

1. Very different permissions

If one assistant can access highly sensitive sources and another cannot, separate agents or at least hard-isolated profiles may make sense.

2. Very different behavior models

If one must behave like:

a strict governed financial analyst,
and another like:
a flexible exploratory data scientist,
then stronger separation can help.
3. Very different tool universes

If one “agent” only does document extraction and another only does heavy data pipelines, a profile may still work, but at some point separation may be cleaner.

4. Very different user journeys

If users clearly enter distinct products, like:

“chat analytics assistant”
“scheduled pipeline builder”
“document audit assistant”

then separate agents/products can make sense.

But that is usually later, not first.

What I would avoid

I would avoid building:

6 separate agents
each with its own overlapping tools and memory
each with slightly different prompts and skills

That often becomes messy fast.

Why:

duplicated logic
unclear ownership
inconsistent answers
hard-to-debug routing
hard-to-maintain policies
Better architecture: capability bundles

Instead of separate agents, define capability bundles or topics.

For example:

Finance Analysis

Enabled:

SQL
Python
finance metric skills
finance workflow skills
finance validation policies
Document + Data Reconciliation

Enabled:

doc reading
table extraction
source querying
reconciliation workflows
Heavy Data Processing

Enabled:

distributed runtime
async jobs
data engineering workflows
stricter execution routing
General Exploration

Enabled:

broad set of tools
lighter guardrails
generic analytics skills

This is probably what you want.

Strong practical recommendation

For MVP, I would implement:

One agent

Single orchestration core.

Topic/profile selection

At session start or inferred dynamically.

Each profile contains:

allowed tool set
preferred skill set
active policies
workflow definitions
default connections if relevant
Optional dynamic topic switching

Inside a session, the system can activate another topic pack if the user’s request shifts.

For example:

starts in Finance Analysis
later needs large-scale processing
activates Heavy Data Processing policies and workflows

That is much better than forcing the user to switch agents manually.
My recommendation for your architecture

Add a concept like:

TopicProfile
interface TopicProfile {
  id: string;
  name: string;
  description?: string;
  status: "active" | "disabled";

  allowedToolNames: string[];
  preferredSkillIds?: string[];
  activePolicyIds?: string[];
  workflowDefinitionIds?: string[];

  defaultConnectionIds?: string[];
  preferredRuntimeTypes?: string[];

  domains?: string[];
  metadata?: Record<string, unknown>;
}

Then a session can have:

one selected topic profile,
or multiple active topic profiles.

This fits your architecture very naturally.

Separate agents are usually worth it only when the boundary is very strong:

different trust zone,
different product,
different permissions,
or radically different workflows.

# User is assigned topics
Topics are not hard-bound to sessions. Instead, each user is granted access to a set of topic profiles, and the orchestration layer dynamically activates the relevant subset of those topics per request or execution step. Topic profiles define the tools, skills, workflows, policies, connections, and runtime types that may be used when that topic is active.

A topic is a capability/governance bundle:
tools
skills
workflows
policies
preferred runtimes
maybe preferred connections

Recommended contracts

Instead of storing session.topic_id, I’d do this:

TopicProfile
interface TopicProfile {
  id: string;
  name: string;
  status: "active" | "disabled";

  allowedToolNames: string[];
  allowedConnectionIds?: string[];
  allowedRuntimeTypes?: string[];

  activeSkillIds?: string[];
  activeWorkflowIds?: string[];
  activePolicyIds?: string[];

  metadata?: Record<string, unknown>;
}
UserTopicAssignment
interface UserTopicAssignment {
  userId: string;
  topicProfileId: string;
  status: "active" | "disabled";
  grantedAt: string;
  grantedBy?: string;

  overrides?: {
    allowedToolNames?: string[];
    deniedToolNames?: string[];
    allowedConnectionIds?: string[];
    deniedConnectionIds?: string[];
    allowedRuntimeTypes?: string[];
    deniedRuntimeTypes?: string[];
  };
}
Optional: TurnTopicActivation

Only if you want observability/debugging.

interface TurnTopicActivation {
  sessionId: string;
  messageId: string;
  topicProfileId: string;
  reason?: string;
  activatedAt: string;
}

This table is optional, but useful for:

debugging
audit
explaining behavior
analytics on usage
Resolution flow

When a new request arrives:

get user’s allowed topics
infer relevant topics from:
request text
selected connections
requested outputs
prior artifacts
intersect:
relevant topics
user-allowed topics
activate corresponding:
tools
skills
workflows
policies
execute only within that resulting capability set

That is the clean flow.

Important rule

The agent should not activate a topic just because it seems useful unless:

the user is allowed that topic
and policies permit it

So activation is:

dynamic
but still bounded
What to store in the session then?

If you do not want a hard-coded topic per session, the session can simply store:

session metadata
messages
artifacts
executions
jobs

And optionally:

recent active topics
topic activation history

But not:

one mandatory session topic