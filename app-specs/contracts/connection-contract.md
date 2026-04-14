type ConnectionType =
  | "postgresql"
  | "mysql"
  | "sqlserver"
  | "oracle"
  | "snowflake"
  | "bigquery"
  | "redshift"
  | "databricks_sql"
  | "s3"
  | "adls"
  | "gcs"
  | "api"
  | "sharepoint"
  | "file_store"
  | "custom";

type ConnectionStatus =
  | "active"
  | "disabled"
  | "deprecated"
  | "error";

type AuthMethod =
  | "username_password"
  | "access_token"
  | "oauth2"
  | "service_account"
  | "iam_role"
  | "managed_identity"
  | "api_key"
  | "secret_ref"
  | "custom";

interface Connection {
  id: string;
  name: string;
  displayName?: string;
  description?: string;

  type: ConnectionType;
  status: ConnectionStatus;

  environment?: string;
  ownerId?: string;
  workspaceId?: string;

  endpoint: ConnectionEndpoint;
  authentication: ConnectionAuthentication;

  capabilities: ConnectionCapabilities;
  runtimePolicy: ConnectionRuntimePolicy;

  attachedSkillIds?: string[];
  tags?: string[];
  metadata?: Record<string, unknown>;

  governance?: ConnectionGovernance;

  createdAt: string;
  updatedAt?: string;
}

interface ConnectionEndpoint {
  host?: string;
  port?: number;
  database?: string;
  schema?: string;
  warehouse?: string;
  account?: string;
  region?: string;
  path?: string;
  baseUrl?: string;

  options?: Record<string, string | number | boolean>;
}

interface ConnectionAuthentication {
  method: AuthMethod;

  secretRef?: string;
  usernameRef?: string;
  passwordRef?: string;
  tokenRef?: string;
  apiKeyRef?: string;

  roleArn?: string;
  serviceAccountRef?: string;
  managedIdentityId?: string;

  additionalAuthParams?: Record<string, unknown>;
}

interface ConnectionCapabilities {
  allowedOperations: ConnectionOperation[];
  supportsMetadataRead?: boolean;
  supportsQueryPushdown?: boolean;
  supportsWrite?: boolean;
  supportsBulkRead?: boolean;
  supportsBulkWrite?: boolean;
  supportsTemporaryObjects?: boolean;
}

type ConnectionOperation =
  | "read"
  | "write"
  | "query"
  | "metadata_read"
  | "create_temp_object"
  | "execute_procedure"
  | "list_objects"
  | "download"
  | "upload";

interface ConnectionRuntimePolicy {
  allowedRuntimeTypes: string[];
  preferredRuntimeType?: string;

  deniedRuntimeTypes?: string[];
  requiresIsolatedRuntime?: boolean;

  credentialInjectionMode?: "ephemeral" | "session_scoped" | "runtime_scoped";
  maxSessionBindings?: number;
}

interface ConnectionGovernance {
  classification?: "public" | "internal" | "confidential" | "restricted";
  allowedUserIds?: string[];
  allowedWorkspaceIds?: string[];

  requireApprovalForWrite?: boolean;
  requireAuditLogging?: boolean;
  maskingPolicy?: string;

  networkPolicy?: {
    allowedRegions?: string[];
    privateOnly?: boolean;
  };
}