"""Phase 3 migration: skills table + connection auth columns."""

from sqlalchemy import text

from shared.db import get_engine


def migrate() -> None:
    engine = get_engine()

    with engine.connect() as conn:
        # Skills table
        conn.execute(text("""
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
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category)"
        ))

        # Connection auth columns
        conn.execute(text(
            "ALTER TABLE connections ADD COLUMN IF NOT EXISTS auth_method VARCHAR(50)"
        ))
        conn.execute(text(
            "ALTER TABLE connections ADD COLUMN IF NOT EXISTS auth_config JSONB NOT NULL DEFAULT '{}'"
        ))

        conn.commit()
        print("Phase 3 migration complete.")


if __name__ == "__main__":
    migrate()
