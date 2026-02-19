import logging
import ssl as ssl_module

import sqlalchemy.exc
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from src.config import settings

logger = logging.getLogger(__name__)

# Naming convention for constraints
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


# Enable SSL for remote database hosts (e.g. NeonDB)
_db_url = settings.db_url
_connect_args: dict = {}
_is_remote = "localhost" not in _db_url and "127.0.0.1" not in _db_url and "db:" not in _db_url
if _is_remote:
    _ssl_ctx = ssl_module.create_default_context()
    if not settings.DATABASE_SSL_VERIFY:
        _ssl_ctx.check_hostname = False
        _ssl_ctx.verify_mode = ssl_module.CERT_NONE
    _connect_args["ssl"] = _ssl_ctx

# Create async engine
engine = create_async_engine(
    _db_url,
    echo=False,
    future=True,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args=_connect_args,
)

# Create async session factory
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
        # Enable pgvector extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
