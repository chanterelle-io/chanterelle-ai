type ExecutionMode = "interactive" | "deferred";
type ExecutionPriority = "low" | "normal" | "high";

interface ExecutionRequest {
  id: string;
  sessionId: string;
  userId: string;

  tool: ToolInvocation;
  target?: ExecutionTarget;

  inputArtifacts?: ExecutionArtifactInput[];
  parameters?: Record<string, unknown>;

  requestedRuntimeType?: string;
  selectedSkillIds?: string[];

  executionModePreference?: ExecutionMode;
  priority?: ExecutionPriority;

  policyContext?: ExecutionPolicyContext;
  expectedOutputs?: ExpectedOutput[];

  requestedBy: {
    actor: "agent" | "user" | "system";
    agentTurnId?: string;
  };

  metadata?: Record<string, unknown>;
}

interface ToolInvocation {
  toolName: string;
  operation: string;
  payload: Record<string, unknown>;
}

interface ExecutionTarget {
  connectionId?: string;
  sourceObject?: string;
  workspaceId?: string;
}

interface ExecutionArtifactInput {
  artifactId: string;
  alias?: string;
  mode?: "read" | "read_write";
  projection?: {
    columns?: string[];
    filterExpression?: string;
    limit?: number;
  };
}

interface ExecutionPolicyContext {
  estimatedDataSizeBytes?: number;
  estimatedRowCount?: number;
  expectedDurationSeconds?: number;
  sensitivityLevel?: "low" | "medium" | "high";
  allowedOperations?: string[];
  requireAsyncAboveSeconds?: number;
}

interface ExpectedOutput {
  name: string;
  type: ArtifactType;
  required: boolean;
  formatHint?: string;
}