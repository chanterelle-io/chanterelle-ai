"""Phase 2 migration: add sessions and runtimes tables."""

from sqlalchemy import text

from shared.db import get_engine


def migrate():
    engine = get_engine()

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR(255) PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ,
                messages JSONB NOT NULL DEFAULT '[]',
                artifact_ids JSONB NOT NULL DEFAULT '[]',
                metadata JSONB NOT NULL DEFAULT '{}'
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS runtimes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL UNIQUE,
                display_name VARCHAR(255),
                type VARCHAR(50) NOT NULL,
                endpoint_url VARCHAR(1024) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                capabilities JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        conn.commit()
        print("Phase 2 migration complete: sessions + runtimes tables created.")


if __name__ == "__main__":
    migrate()
