CREATE TABLE IF NOT EXISTS connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    type VARCHAR(50) NOT NULL DEFAULT 'table',
    status VARCHAR(50) NOT NULL DEFAULT 'ready',
    storage_uri VARCHAR(1024),
    size_bytes BIGINT,
    format_info JSONB,
    schema_info JSONB,
    statistics JSONB,
    lineage JSONB,
    retention_class VARCHAR(50) NOT NULL DEFAULT 'temporary',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    extra_metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_name ON artifacts(session_id, name);

-- Phase 2: Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    messages JSONB NOT NULL DEFAULT '[]',
    artifact_ids JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}'
);

-- Phase 2: Runtime Registry
CREATE TABLE IF NOT EXISTS runtimes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    type VARCHAR(50) NOT NULL,
    endpoint_url VARCHAR(1024) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    capabilities JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Phase 3: Skills
CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    title VARCHAR(255),
    description TEXT,
    scope JSONB NOT NULL DEFAULT '{}',
    triggers JSONB NOT NULL DEFAULT '[]',
    instructions JSONB NOT NULL DEFAULT '{}',
    tags JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);

-- Phase 3: Credential store
ALTER TABLE connections ADD COLUMN IF NOT EXISTS auth_method VARCHAR(50);
ALTER TABLE connections ADD COLUMN IF NOT EXISTS auth_config JSONB NOT NULL DEFAULT '{}';

-- Phase 4: Policies
CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    description TEXT,
    version VARCHAR(50),
    scope JSONB NOT NULL DEFAULT '{}',
    condition JSONB NOT NULL DEFAULT '{}',
    effect JSONB NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 0,
    tags JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_policies_type ON policies(type);

-- Phase 4: Topic Profiles
CREATE TABLE IF NOT EXISTS topic_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    allowed_tool_names JSONB NOT NULL DEFAULT '[]',
    allowed_connection_names JSONB NOT NULL DEFAULT '[]',
    allowed_runtime_types JSONB NOT NULL DEFAULT '[]',
    active_skill_ids JSONB NOT NULL DEFAULT '[]',
    active_policy_ids JSONB NOT NULL DEFAULT '[]',
    domains JSONB NOT NULL DEFAULT '[]',
    tags JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- Phase 4: User-Topic Assignments
CREATE TABLE IF NOT EXISTS user_topic_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    topic_profile_id UUID NOT NULL REFERENCES topic_profiles(id),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_user_topic_user ON user_topic_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_user_topic_profile ON user_topic_assignments(topic_profile_id);

-- Phase 5: Jobs
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'submitted',
    execution_request JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    logs JSONB NOT NULL DEFAULT '[]',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
