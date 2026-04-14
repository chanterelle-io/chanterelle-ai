type WorkflowStatus = "active" | "disabled" | "deprecated";

interface WorkflowDefinition {
  id: string;
  name: string;
  version: string;
  status: WorkflowStatus;

  title?: string;
  description?: string;

  triggers: WorkflowTrigger;
  steps: WorkflowStep[];

  requiredSkillIds?: string[];
  activePolicyIds?: string[];
  outputExpectations?: string[];

  scope?: WorkflowScope;
  tags?: string[];
  metadata?: Record<string, unknown>;

  createdAt: string;
  updatedAt?: string;
}

interface WorkflowTrigger {
  taskTypes?: string[];
  keywords?: string[];
  domains?: string[];
  topicProfileIds?: string[];
}

interface WorkflowScope {
  level: "global" | "workspace" | "domain";
  workspaceIds?: string[];
  domains?: string[];
}

interface WorkflowStep {
  stepId: string;
  order: number;
  title: string;
  description: string;

  preferredTool?: string;
  preferredRuntimeType?: string;

  inputExpectations?: string[];
  outputExpectations?: string[];
  validationRules?: string[];

  isOptional?: boolean;
  condition?: string;

  fallback?: WorkflowStepFallback;
}

interface WorkflowStepFallback {
  description: string;
  alternativeTool?: string;
  alternativeRuntimeType?: string;
}
