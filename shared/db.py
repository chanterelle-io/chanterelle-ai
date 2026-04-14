from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from shared.settings import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)
    return _engine
