from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base


def _create_engine():
    kwargs: dict = {'pool_pre_ping': True}
    connect_args: dict = {}
    if settings.postgres_sslmode:
        connect_args['sslmode'] = settings.postgres_sslmode
    if connect_args:
        kwargs['connect_args'] = connect_args
    return create_engine(settings.postgres_dsn, **kwargs)


engine = _create_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Import models so metadata is populated, then create tables."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
