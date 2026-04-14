type RuntimeMode = "interactive" | "deferred" | "both";

interface RuntimeDefinition {
  id: string;
  name: string;
  runtimeType: string;
  version: string;

  image: RuntimeImage;
  environment: RuntimeEnvironment;

  supportedConnectionTypes: ConnectionType[];
  supportedOperations: string[];

  dependencyProfile: RuntimeDependencyProfile;
  resourceProfile: RuntimeResourceProfile;
  isolationProfile: RuntimeIsolationProfile;

  executionMode: RuntimeMode;
  tags?: string[];
  metadata?: Record<string, unknown>;

  status: "active" | "deprecated" | "disabled";
}

interface RuntimeImage {
  imageRef: string;
  imageDigest?: string;
  baseOs?: string;
}

interface RuntimeEnvironment {
  pythonVersion?: string;
  javaVersion?: string;
  nodeVersion?: string;

  envVars?: Record<string, string>;
  workingDirectory?: string;
}

interface RuntimeDependencyProfile {
  pythonPackages?: string[];
  systemPackages?: string[];
  jdbcDrivers?: string[];
  odbcDrivers?: string[];
  connectorLibraries?: string[];
}

interface RuntimeResourceProfile {
  cpuCores?: number;
  memoryGb?: number;
  diskGb?: number;
  gpuCount?: number;

  autoscalingEnabled?: boolean;
  minWorkers?: number;
  maxWorkers?: number;
}

interface RuntimeIsolationProfile {
  isolationLevel: "process" | "container" | "vm" | "job_cluster";
  networkRestricted?: boolean;
  internetAccess?: boolean;
  persistentDisk?: boolean;
  sessionScoped?: boolean;
}

type RuntimeInstanceStatus =
  | "starting"
  | "ready"
  | "busy"
  | "idle"
  | "stopping"
  | "stopped"
  | "error";

interface RuntimeInstance {
  id: string;
  runtimeDefinitionId: string;
  runtimeType: string;

  status: RuntimeInstanceStatus;

  sessionId?: string;
  boundConnectionIds?: string[];

  createdAt: string;
  lastUsedAt?: string;

  endpoint?: {
    internalUrl?: string;
    jobId?: string;
  };

  resourceAllocation?: {
    cpuCores?: number;
    memoryGb?: number;
    diskGb?: number;
  };

  metadata?: Record<string, unknown>;
}