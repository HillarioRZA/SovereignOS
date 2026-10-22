"""
Single-Writer Exclusive State Lease & Heartbeat Manager.
Menjamin integritas penulisan eksklusif proses gateway dengan pembaruan heartbeat periodik.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import os
from typing import Optional
import aiosqlite

from app.core.logger import logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


async def acquire_lease(
    conn: aiosqlite.Connection,
    lease_key: str = "primary_gateway_writer",
    owner_process_id: Optional[str] = None,
    duration_seconds: int = 10,
    wal_inode: Optional[str] = None,
) -> bool:
    """Mengakuisisi hak tulis eksklusif atomik.
    
    Berhasil jika:
    1. Belum ada lease untuk key tersebut, ATAU
    2. Lease sebelumnya telah kedaluwarsa (expires_at < waktu sekarang).
    """
    pid = owner_process_id or f"proc_{os.getpid()}_{id(asyncio.current_task())}"
    now_str = _now_iso()
    exp_str = _future_iso(duration_seconds)

    # Cek lease yang ada
    cur = await conn.execute(
        "SELECT owner_process_id, generation_id, expires_at FROM state_leases WHERE lease_key = ?",
        (lease_key,),
    )
    row = await cur.fetchone()

    if row is None:
        await conn.execute(
            """
            INSERT INTO state_leases 
            (lease_key, owner_process_id, generation_id, wal_inode, acquired_at, heartbeat_at, expires_at)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            """,
            (lease_key, pid, wal_inode, now_str, now_str, exp_str),
        )
        await conn.commit()
        logger.info(f"Lease [{lease_key}] berhasil diakuisisi oleh process [{pid}] (Gen 1).")
        return True

    # Jika sudah dimiliki proses ini
    if row["owner_process_id"] == pid:
        await conn.execute(
            "UPDATE state_leases SET heartbeat_at = ?, expires_at = ? WHERE lease_key = ? AND owner_process_id = ?",
            (now_str, exp_str, lease_key, pid),
        )
        await conn.commit()
        return True

    # Jika dimiliki proses lain, cek apakah sudah kedaluwarsa
    expires_at_str = row["expires_at"]
    try:
        exp_dt = datetime.fromisoformat(expires_at_str)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    except Exception:
        exp_dt = datetime.min.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > exp_dt:
        next_gen = row["generation_id"] + 1
        await conn.execute(
            """
            UPDATE state_leases
            SET owner_process_id = ?, generation_id = ?, wal_inode = ?,
                acquired_at = ?, heartbeat_at = ?, expires_at = ?
            WHERE lease_key = ?
            """,
            (pid, next_gen, wal_inode, now_str, now_str, exp_str, lease_key),
        )
        await conn.commit()
        logger.warning(
            f"Lease [{lease_key}] kedaluwarsa diambil alih oleh [{pid}] (Gen {next_gen})."
        )
        return True

    logger.debug(f"Gagal akuisisi lease [{lease_key}]: dipegang [{row['owner_process_id']}].")
    return False


async def renew_lease(
    conn: aiosqlite.Connection,
    lease_key: str = "primary_gateway_writer",
    owner_process_id: Optional[str] = None,
    duration_seconds: int = 10,
) -> bool:
    """Memperbarui heartbeat lease aktif."""
    pid = owner_process_id or f"proc_{os.getpid()}"
    now_str = _now_iso()
    exp_str = _future_iso(duration_seconds)

    cur = await conn.execute(
        """
        UPDATE state_leases
        SET heartbeat_at = ?, expires_at = ?
        WHERE lease_key = ? AND owner_process_id = ?
        """,
        (now_str, exp_str, lease_key, pid),
    )
    await conn.commit()
    return cur.rowcount > 0


async def release_lease(
    conn: aiosqlite.Connection,
    lease_key: str = "primary_gateway_writer",
    owner_process_id: Optional[str] = None,
) -> bool:
    """Melepaskan lease secara bersih saat proses shutdown."""
    pid = owner_process_id or f"proc_{os.getpid()}"
    cur = await conn.execute(
        "DELETE FROM state_leases WHERE lease_key = ? AND owner_process_id = ?",
        (lease_key, pid),
    )
    await conn.commit()
    if cur.rowcount > 0:
        logger.info(f"Lease [{lease_key}] dilepaskan oleh [{pid}].")
        return True
    return False


class StateLeaseDaemon:
    """Daemon background untuk memelihara heartbeat lease setiap 3 detik."""

    def __init__(
        self,
        lease_key: str = "primary_gateway_writer",
        owner_id: Optional[str] = None,
        duration_seconds: int = 10,
        heartbeat_interval: float = 3.0,
    ) -> None:
        self.lease_key = lease_key
        self.owner_id = owner_id or f"proc_{os.getpid()}_{id(self)}"
        self.duration_seconds = duration_seconds
        self.interval = heartbeat_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self, get_conn_factory) -> bool:
        """Mencoba akuisisi lease dan memulai loop heartbeat jika berhasil."""
        async with get_conn_factory() as conn:
            acquired = await acquire_lease(
                conn, self.lease_key, self.owner_id, self.duration_seconds
            )
            if not acquired:
                return False

        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop(get_conn_factory))
        return True

    async def _heartbeat_loop(self, get_conn_factory) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                if not self._running:
                    break
                async with get_conn_factory() as conn:
                    ok = await renew_lease(
                        conn, self.lease_key, self.owner_id, self.duration_seconds
                    )
                    if not ok:
                        logger.error(f"Gagal memperbarui heartbeat lease [{self.lease_key}].")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error pada loop heartbeat lease: {e}")

    async def stop(self, get_conn_factory) -> None:
        """Menghentikan heartbeat dan melepaskan lease."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        try:
            async with get_conn_factory() as conn:
                await release_lease(conn, self.lease_key, self.owner_id)
        except Exception as e:
            logger.warning(f"Error saat pelepasan lease shutdown: {e}")
