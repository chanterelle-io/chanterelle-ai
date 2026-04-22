"""Phase 5 migration: add jobs table."""

from sqlalchemy import text
from shared.db import get_engine


def migrate():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
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
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"))
        conn.commit()
    print("Phase 5 migration complete: jobs table created.")


if __name__ == "__main__":
    migrate()
