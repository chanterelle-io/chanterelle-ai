type SkillCategory =
  | "connector"
  | "metric"
  | "workflow"
  | "domain"
  | "compliance";

type SkillStatus = "active" | "deprecated" | "disabled";

interface Skill {
  id: string;
  name: string;
  version: string;
  category: SkillCategory;
  status: SkillStatus;

  title?: string;
  description: string;

  scope: SkillScope;
  triggers?: SkillTrigger[];

  instructions: SkillInstructions;
  helperAssets?: SkillHelperAsset[];
  validations?: SkillValidation[];

  tags?: string[];
  metadata?: Record<string, unknown>;
}

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

interface SkillTrigger {
  kind: "keyword" | "source_match" | "task_match" | "connection_match";
  value: string;
  weight?: number;
}

interface SkillInstructions {
  summary: string;
  detailedMarkdown?: string;
  recommendedSteps?: string[];
  dos?: string[];
  donts?: string[];
  outputExpectations?: string[];
}

interface SkillHelperAsset {
  id: string;
  type: "sql_template" | "python_helper" | "reference_doc" | "example_artifact";
  name: string;
  uri: string;
  description?: string;
}

interface SkillValidation {
  id: string;
  description: string;
  kind: "schema_check" | "aggregation_check" | "null_check" | "business_rule";
  rule: string;
  severity: "info" | "warning" | "error";
}