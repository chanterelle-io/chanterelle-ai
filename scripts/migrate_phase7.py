"""Phase 7 migration: add workflow registry support."""

from sqlalchemy import text

from shared.db import get_engine


def migrate():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflows (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL UNIQUE,
                version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                title VARCHAR(255),
                description TEXT,
                triggers JSONB NOT NULL DEFAULT '{}',
                steps JSONB NOT NULL DEFAULT '[]',
                required_skill_ids JSONB NOT NULL DEFAULT '[]',
                active_policy_ids JSONB NOT NULL DEFAULT '[]',
                output_expectations JSONB NOT NULL DEFAULT '[]',
                scope JSONB NOT NULL DEFAULT '{}',
                tags JSONB NOT NULL DEFAULT '[]',
                metadata JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)"))
        conn.commit()
    print("Phase 7 migration complete: workflow registry support applied.")


if __name__ == "__main__":
    migrate()