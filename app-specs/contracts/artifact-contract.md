type ArtifactType =
  | "table"
  | "file"
  | "chart"
  | "report"
  | "text"
  | "model_output"
  | "execution_log"
  | "reference";

type RetentionClass =
  | "temporary"
  | "reusable"
  | "pinned"
  | "persistent";

type ArtifactStatus =
  | "ready"
  | "pending"
  | "failed"
  | "deleted"
  | "expired";

interface Artifact {
  id: string;
  sessionId: string;
  workspaceId?: string;

  name: string;
  displayName?: string;
  description?: string;

  type: ArtifactType;
  subtype?: string;

  status: ArtifactStatus;
  createdAt: string;
  updatedAt?: string;
  expiresAt?: string;

  createdBy: {
    kind: "user" | "tool" | "system";
    actorId?: string;
    executionId?: string;
    toolName?: string;
  };

  storage: ArtifactStorage;
  format?: ArtifactFormat;

  schema?: TableSchema;
  statistics?: ArtifactStatistics;

  lineage?: ArtifactLineage;
  tags?: string[];
  retention: ArtifactRetention;

  access: ArtifactAccess;
  references?: ArtifactReference[];

  preview?: ArtifactPreview;
  metadata?: Record<string, unknown>;
}

interface ArtifactStorage {
  backend: "object_storage" | "inline" | "external_reference";
  uri: string;
  sizeBytes?: number;
  checksum?: string;
  version?: string;
  region?: string;
}

interface ArtifactFormat {
  mediaType?: string;
  encoding?: string;
  tableFormat?: "parquet" | "csv" | "arrow" | "delta" | "iceberg";
}

interface TableSchema {
  columns: SchemaColumn[];
  primaryKey?: string[];
  partitionColumns?: string[];
  timeColumn?: string;
  semanticHints?: Record<string, string>;
  schemaVersion?: string;
}

interface SchemaColumn {
  name: string;
  logicalType: string;
  physicalType?: string;
  nullable?: boolean;
  description?: string;
  semanticRole?: string;
}

interface ArtifactStatistics {
  rowCount?: number;
  columnCount?: number;
  byteSize?: number;
  minValues?: Record<string, unknown>;
  maxValues?: Record<string, unknown>;
  distinctCounts?: Record<string, number>;
  nullCounts?: Record<string, number>;
}

interface ArtifactLineage {
  sourceKind: "uploaded" | "connected_source" | "derived" | "manual" | "system";
  sourceRefs?: SourceReference[];
  parentArtifactIds?: string[];
  transformationSummary?: string;
  producingSkillIds?: string[];
}

interface SourceReference {
  sourceId: string;
  sourceType?: string;
  objectName?: string;
  queryText?: string;
}

interface ArtifactRetention {
  class: RetentionClass;
  evictionPriority?: number;
  pinnedByUser?: boolean;
  lastAccessedAt?: string;
}

interface ArtifactAccess {
  ownerUserId?: string;
  sharedWith?: string[];
  readableByAgent: boolean;
  readableByRuntimes: string[];
}

interface ArtifactReference {
  artifactId: string;
  relation: "input" | "derived_from" | "preview_of" | "export_of";
}

interface ArtifactPreview {
  available: boolean;
  sampleRowsUri?: string;
  textSnippet?: string;
}