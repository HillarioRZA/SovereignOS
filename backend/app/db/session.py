"""
Dual-Engine Database Session & Connection Management.
Mengelola koneksi aiosqlite asinkron (WAL Mode) dan opsi PostgreSQL asyncpg.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Union, Any
import aiosqlite

try:
    import asyncpg  # type: ignore
except ImportError:
    asyncpg = None

from app.core.config import settings
from app.core.logger import logger

_pg_pool: Optional[Any] = None


def resolve_db_path(custom_path: Optional[str] = None) -> str:
    """Menentukan path file database SQLite dan memastikan direktori induk tersedia."""
    if custom_path:
        db_file = Path(custom_path)
    else:
        raw = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        db_file = Path(raw)

    if not db_file.parent.exists():
        db_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Direktori database dibuat: {db_file.parent}")
    return str(db_file.resolve())


async def init_pg_pool() -> None:
    """Menginisialisasi connection pool asyncpg jika POSTGRES_DSN disetel."""
    global _pg_pool
    if settings.POSTGRES_DSN and asyncpg and not _pg_pool:
        _pg_pool = await asyncpg.create_pool(dsn=settings.POSTGRES_DSN, min_size=2, max_size=10)
        logger.info("PostgreSQL asyncpg connection pool berhasil diinisialisasi.")


async def close_pg_pool() -> None:
    """Menutup connection pool asyncpg."""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("PostgreSQL asyncpg connection pool ditutup.")


@asynccontextmanager
async def get_db_connection(
    custom_path: Optional[str] = None,
) -> AsyncGenerator[Union[aiosqlite.Connection, Any], None]:
    """Context manager asinkron untuk koneksi database Dual-Engine.
    
    Default: SQLite WAL dengan PRAGMA teroptimasi.
    Fallback: PostgreSQL pool jika POSTGRES_DSN disetel dan custom_path tidak diisi.
    """
    if settings.POSTGRES_DSN and not custom_path and _pg_pool:
        async with _pg_pool.acquire() as pg_conn:
            yield pg_conn
        return

    db_path = resolve_db_path(custom_path)
    try:
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode = WAL;")
            await conn.execute("PRAGMA synchronous = NORMAL;")
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.execute("PRAGMA busy_timeout = 5000;")
            yield conn
    except aiosqlite.Error as err:
        logger.error(f"Kesalahan koneksi SQLite WAL ({db_path}): {err}")
        raise
