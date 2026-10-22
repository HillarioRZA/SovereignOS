"""
FD-Aware Readonly Connection Pool.
Mengalokasikan pool koneksi read-only SQLite (PRAGMA query_only=ON) sesuai anggaran File Descriptor OS.
"""

import asyncio
from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator, Optional
import aiosqlite

from app.core.logger import logger
from app.db.session import resolve_db_path

try:
    import resource
except ImportError:
    resource = None


def _calculate_read_budget() -> int:
    """Menghitung batas koneksi pembaca berdasarkan ulimit OS atau default yang aman."""
    if resource and hasattr(resource, "RLIMIT_NOFILE"):
        try:
            soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            # Alokasikan maksimal 10% dari ulimit untuk read pool
            budget = max(4, min(int(soft_limit * 0.1), 32))
            return budget
        except Exception:
            pass
    # Windows atau fallback default
    return 8


class ReadonlyConnectionPool:
    """Pool koneksi asinkron khusus pembacaan murni."""

    def __init__(self, db_path: Optional[str] = None, max_connections: Optional[int] = None) -> None:
        self.db_path = db_path
        self.max_connections = max_connections or _calculate_read_budget()
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()
        self._all_conns: list[aiosqlite.Connection] = []
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Membuka koneksi read-only sesuai batas anggaran."""
        async with self._lock:
            if self._initialized:
                return
            path = resolve_db_path(self.db_path)
            for _ in range(self.max_connections):
                conn = await aiosqlite.connect(path)
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode = WAL;")
                await conn.execute("PRAGMA synchronous = NORMAL;")
                await conn.execute("PRAGMA query_only = ON;")
                await conn.execute("PRAGMA busy_timeout = 3000;")
                self._all_conns.append(conn)
                await self._pool.put(conn)
            self._initialized = True
            logger.info(
                f"ReadonlyConnectionPool diinisialisasi dengan {self.max_connections} koneksi (query_only=ON)."
            )

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Meminjam koneksi read-only dari pool."""
        if not self._initialized:
            await self.initialize()

        conn = await self._pool.get()
        try:
            yield conn
        finally:
            await self._pool.put(conn)

    async def close(self) -> None:
        """Menutup seluruh koneksi pembaca saat shutdown."""
        async with self._lock:
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except asyncio.QueueEmpty:
                    break
            for conn in self._all_conns:
                try:
                    await conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
            self._initialized = False
            logger.info("ReadonlyConnectionPool berhasil ditutup.")


# Singleton read pool
_global_read_pool: Optional[ReadonlyConnectionPool] = None


async def get_read_pool(db_path: Optional[str] = None) -> ReadonlyConnectionPool:
    """Mengembalikan atau menginisialisasi singleton ReadonlyConnectionPool."""
    global _global_read_pool
    if _global_read_pool is None:
        _global_read_pool = ReadonlyConnectionPool(db_path=db_path)
        await _global_read_pool.initialize()
    return _global_read_pool


@asynccontextmanager
async def get_read_connection(db_path: Optional[str] = None) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Helper context manager untuk kueri baca."""
    pool = await get_read_pool(db_path)
    async with pool.acquire() as conn:
        yield conn
