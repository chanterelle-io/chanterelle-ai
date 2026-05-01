"""Phase 8 migration: add topic-profile workflow activation fields."""

from sqlalchemy import text

from shared.db import get_engine


def migrate():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE topic_profiles
            ADD COLUMN IF NOT EXISTS active_workflow_ids JSONB NOT NULL DEFAULT '[]'
        """))
        conn.commit()
    print("Phase 8 migration complete: topic-profile workflow activation applied.")


if __name__ == "__main__":
    migrate()