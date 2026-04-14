type PolicyType =
  | "execution_routing"
  | "tool_selection"
  | "validation"
  | "security"
  | "workflow_preference"
  | "response_requirement";

type PolicyStatus = "active" | "disabled" | "deprecated";

interface Policy {
  id: string;
  name: string;
  type: PolicyType;
  status: PolicyStatus;

  description?: string;
  version?: string;

  scope: PolicyScope;
  condition: PolicyCondition;
  effect: PolicyEffect;

  priority?: number;
  tags?: string[];
  metadata?: Record<string, unknown>;

  createdAt: string;
  updatedAt?: string;
}

interface PolicyScope {
  level: "global" | "workspace" | "domain" | "connection";
  workspaceIds?: string[];
  connectionIds?: string[];
  taskTypes?: string[];
  domains?: string[];
  topicProfileIds?: string[];
}

interface PolicyCondition {
  // Conditions are type-specific.
  // The execution layer evaluates these against the current request context.

  // Execution routing conditions
  estimatedRowCountAbove?: number;
  estimatedDataSizeBytesAbove?: number;
  expectedDurationSecondsAbove?: number;
  sourceTypes?: string[];
  sensitivityLevels?: string[];

  // Task/tool conditions
  taskTypes?: string[];
  toolNames?: string[];
  operationTypes?: string[];

  // Domain conditions
  domains?: string[];
  keywords?: string[];

  // Custom conditions
  custom?: Record<string, unknown>;
}

interface PolicyEffect {
  // What happens when the condition matches.

  // Execution routing effects
  forceExecutionMode?: "interactive" | "deferred";
  preferredRuntimeType?: string;
  deniedRuntimeTypes?: string[];
  requireIsolatedRuntime?: boolean;

  // Skill/validation effects
  requiredSkillIds?: string[];
  requiredValidationIds?: string[];

  // Tool effects
  deniedToolNames?: string[];
  requiredToolNames?: string[];

  // Response effects
  requiredResponseElements?: string[];

  // Approval effects
  requireApproval?: boolean;
  approvalReason?: string;

  // Custom effects
  custom?: Record<string, unknown>;
}
