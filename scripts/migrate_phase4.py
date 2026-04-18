"""Phase 4 migration: policies, topic_profiles, user_topic_assignments tables."""

from sqlalchemy import text
from shared.db import get_engine


def migrate():
    engine = get_engine()
    with engine.connect() as conn:
        # Policies table
        conn.execute(text("""
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
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_policies_type ON policies(type)"
        ))
        print("Created policies table")

        # Topic profiles table
        conn.execute(text("""
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
            )
        """))
        print("Created topic_profiles table")

        # User-topic assignments table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_topic_assignments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id VARCHAR(255) NOT NULL,
                topic_profile_id UUID NOT NULL REFERENCES topic_profiles(id),
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                granted_by VARCHAR(255)
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_user_topic_user ON user_topic_assignments(user_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_user_topic_profile ON user_topic_assignments(topic_profile_id)"
        ))
        print("Created user_topic_assignments table")

        conn.commit()
    print("Phase 4 migration complete.")


if __name__ == "__main__":
    migrate()
