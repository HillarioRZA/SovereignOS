"""
Path-Level Asynchronous Mutex Anti-Race-Condition Manager.
Menjamin modifikasi berkas paralel oleh berbagai agen tidak saling menimpa data.
Kunci dinormalisasi pada level {project_id}:{normalized_path}.
"""

import asyncio
from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator, Dict, Set

from app.core.logger import logger


class FileLockManager:
    """Pengelola mutex asinkron berbasis path untuk mencegah tabrakan tulis berkas."""

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._held_by_project: Dict[str, Set[str]] = {}
        self._global_lock = asyncio.Lock()

    def _normalize(self, file_path: str) -> str:
        """Menormalkan path menjadi string kanonikal terstandarisasi."""
        cleaned = file_path.strip().replace("\\", "/")
        norm = os.path.normpath(cleaned).replace("\\", "/")
        return norm.lstrip("./")

    def _make_key(self, project_id: str, file_path: str) -> str:
        return f"{project_id}:{self._normalize(file_path)}"

    async def _get_or_create_lock(self, key: str, project_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            if project_id not in self._held_by_project:
                self._held_by_project[project_id] = set()
            self._held_by_project[project_id].add(key)
            return self._locks[key]

    async def acquire(self, project_id: str, file_path: str) -> None:
        """Mengakuisisi kunci berkas untuk proyek tertentu."""
        key = self._make_key(project_id, file_path)
        lock = await self._get_or_create_lock(key, project_id)
        await lock.acquire()
        logger.debug(f"[FileLockManager] Acquired lock: {key}")

    def release(self, project_id: str, file_path: str) -> None:
        """Melepaskan kunci berkas jika saat ini sedang dipegang."""
        key = self._make_key(project_id, file_path)
        lock = self._locks.get(key)
        if lock and lock.locked():
            lock.release()
            logger.debug(f"[FileLockManager] Released lock: {key}")

    def release_all_project_locks(self, project_id: str) -> int:
        """Melepaskan seluruh kunci aktif milik suatu proyek (misal saat 1-klik Hold Ticket)."""
        keys = list(self._held_by_project.get(project_id, set()))
        released_count = 0
        for k in keys:
            lock = self._locks.get(k)
            if lock and lock.locked():
                lock.release()
                released_count += 1
                logger.info(f"[FileLockManager] Emergency release: {k}")
        self._held_by_project.pop(project_id, None)
        return released_count

    @asynccontextmanager
    async def lock(self, project_id: str, file_path: str) -> AsyncGenerator[None, None]:
        """Context manager asinkron untuk operasi I/O berkas terproteksi."""
        key = self._make_key(project_id, file_path)
        lock = await self._get_or_create_lock(key, project_id)
        await lock.acquire()
        logger.debug(f"[FileLockManager] Locked via context: {key}")
        try:
            yield
        finally:
            if lock.locked():
                lock.release()
                logger.debug(f"[FileLockManager] Unlocked via context: {key}")


file_lock_manager = FileLockManager()
