import logging
import os
import ssl as ssl_module

import sqlalchemy.exc
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from src.config import settings

logger = logging.getLogger(__name__)

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata


_db_url = settings.db_url
_connect_args: dict = {}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "db", "postgres", "postgresql"}
_pghost = os.getenv("PGHOST", "")

def _is_local_db(url: str) -> bool:
    for host in _LOCAL_HOSTS:
        if host in url:
            return True
    if _pghost and not any(c == '.' for c in _pghost):
        return True
    return False

_is_local = _is_local_db(_db_url)

if not _is_local:
    _ssl_ctx = ssl_module.create_default_context()
    if not settings.DATABASE_SSL_VERIFY:
        _ssl_ctx.check_hostname = False
        _ssl_ctx.verify_mode = ssl_module.CERT_NONE
    _connect_args["ssl"] = _ssl_ctx

# Pool tuning differs by environment:
# - Local Postgres: pre-ping is cheap and catches docker restarts.
# - Neon (remote): pre-ping issues an extra round-trip on every checkout
#   that can wake the compute pointlessly. Rely on pool_recycle instead and
#   keep max_overflow small so idle peaks don't pin extra connections.
engine = create_async_engine(
    _db_url,
    echo=False,
    future=True,
    pool_size=5,
    max_overflow=20 if _is_local else 5,
    pool_pre_ping=_is_local,
    pool_recycle=3600 if _is_local else 1800,
    connect_args=_connect_args,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency for getting async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except (OSError, sqlalchemy.exc.SQLAlchemyError) as exc:
            logger.error("Database session error, rolling back: %s", exc)
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
