"""Phase 6 migration: add artifact retention, session lifecycle, and topic tool updates."""

import json

from sqlalchemy import text

from shared.db import get_engine


def migrate():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ"))

        conn.execute(text("""
            UPDATE artifacts
            SET is_pinned = TRUE
            WHERE retention_class = 'pinned'
        """))
        conn.execute(text("""
            UPDATE artifacts
            SET last_accessed_at = COALESCE(last_accessed_at, created_at)
            WHERE last_accessed_at IS NULL
        """))
        conn.execute(text("""
            UPDATE artifacts
            SET expires_at = created_at + INTERVAL '7 days'
            WHERE expires_at IS NULL
              AND retention_class = 'temporary'
        """))
        conn.execute(text("""
            UPDATE artifacts
            SET expires_at = created_at + INTERVAL '30 days'
            WHERE expires_at IS NULL
              AND retention_class = 'reusable'
              AND is_pinned = FALSE
        """))

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_artifacts_expires_at ON artifacts(expires_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_artifacts_last_accessed_at ON artifacts(last_accessed_at)"))

        conn.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"))
        conn.execute(text("""
            UPDATE sessions
            SET last_accessed_at = COALESCE(last_accessed_at, updated_at, created_at)
            WHERE last_accessed_at IS NULL
        """))
        conn.execute(text("""
            UPDATE sessions
            SET expires_at = COALESCE(expires_at, COALESCE(updated_at, created_at) + INTERVAL '7 days')
            WHERE expires_at IS NULL
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)"))

        conn.execute(
            text("""
                UPDATE topic_profiles
                SET allowed_tool_names = CAST(:allowed_tool_names AS JSONB),
                    updated_at = NOW()
                WHERE name = 'finance_analysis'
            """),
            {
                "allowed_tool_names": json.dumps([
                    "query_sql_source",
                    "inspect_artifact",
                    "pin_artifact",
                    "unpin_artifact",
                ])
            },
        )
        conn.execute(
            text("""
                UPDATE topic_profiles
                SET allowed_tool_names = CAST(:allowed_tool_names AS JSONB),
                    updated_at = NOW()
                WHERE name = 'general_exploration'
            """),
            {
                "allowed_tool_names": json.dumps([
                    "query_sql_source",
                    "transform_with_python",
                    "inspect_artifact",
                    "pin_artifact",
                    "unpin_artifact",
                ])
            },
        )
        conn.commit()
    print("Phase 6 migration complete: artifact retention, session lifecycle, and topic tool updates applied.")


if __name__ == "__main__":
    migrate()