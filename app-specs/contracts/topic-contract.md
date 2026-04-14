type TopicProfileStatus = "active" | "disabled";

interface TopicProfile {
  id: string;
  name: string;
  displayName?: string;
  description?: string;
  status: TopicProfileStatus;

  allowedToolNames: string[];
  allowedConnectionIds?: string[];
  allowedRuntimeTypes?: string[];

  activeSkillIds?: string[];
  activeWorkflowIds?: string[];
  activePolicyIds?: string[];

  domains?: string[];
  tags?: string[];
  metadata?: Record<string, unknown>;

  createdAt: string;
  updatedAt?: string;
}

interface UserTopicAssignment {
  userId: string;
  topicProfileId: string;
  status: "active" | "disabled";

  grantedAt: string;
  grantedBy?: string;

  overrides?: UserTopicOverrides;
}

interface UserTopicOverrides {
  allowedToolNames?: string[];
  deniedToolNames?: string[];
  allowedConnectionIds?: string[];
  deniedConnectionIds?: string[];
  allowedRuntimeTypes?: string[];
  deniedRuntimeTypes?: string[];
}

// Optional: for debugging, audit, and usage analytics.
interface TurnTopicActivation {
  sessionId: string;
  messageId: string;
  topicProfileId: string;
  reason?: string;
  activatedAt: string;
}
