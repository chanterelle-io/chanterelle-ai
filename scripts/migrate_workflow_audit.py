"""Add dedicated workflow audit event storage."""

from sqlalchemy import text

from shared.db import get_engine


def migrate():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_audit_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                message_index INTEGER,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                workflow_trace JSONB NOT NULL DEFAULT '[]',
                workflow_denial_message TEXT,
                artifact_ids JSONB NOT NULL DEFAULT '[]',
                metadata JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_workflow_audit_session "
            "ON workflow_audit_events(session_id, created_at)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_workflow_audit_user "
            "ON workflow_audit_events(user_id, created_at)"
        ))
        conn.commit()
    print("Workflow audit migration complete: dedicated event storage applied.")


if __name__ == "__main__":
    migrate()
