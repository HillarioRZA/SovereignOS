"""
Unit & Concurrency Tests for Dual-Engine Database, State Leases, and Quarantine Store.
"""

import asyncio
import gc
import os
import tempfile
import pytest
import aiosqlite

from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.db.state_lease import acquire_lease, renew_lease, release_lease, StateLeaseDaemon
from app.db.read_pool import ReadonlyConnectionPool
from app.db.quarantine_repair import quarantine_record, run_db_preflight_check


def _safe_remove(path: str) -> None:
    gc.collect()
    for p in [path, f"{path}-wal", f"{path}-shm"]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_sqlite_wal_pragmas_and_ddl():
    """Uji konfigurasi PRAGMA WAL dan eksekusi 28 skema DDL."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async with get_db_connection(db_path) as conn:
            cur = await conn.execute("PRAGMA journal_mode;")
            row = await cur.fetchone()
            assert row[0].upper() == "WAL"

            cur = await conn.execute("PRAGMA foreign_keys;")
            row = await cur.fetchone()
            assert row[0] == 1

            count = await execute_ddl_migrations(conn)
            assert count >= 20

            # Cek tabel-tabel utama terbuat
            tables_to_check = [
                "state_leases", "quarantine_store", "vault_secrets",
                "corporate_roles", "corporate_divisions", "corporate_tickets",
                "corporate_messages", "corporate_token_ledger"
            ]
            for t in tables_to_check:
                cur = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)
                )
                assert (await cur.fetchone()) is not None
    finally:
        _safe_remove(db_path)


@pytest.mark.asyncio
async def test_single_writer_state_lease():
    """Uji eksklusivitas Single-Writer Lease, penolakan proses lain, dan pengambilalihan saat kedaluwarsa."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async with get_db_connection(db_path) as conn:
            await execute_ddl_migrations(conn)

            # Process A mengakuisisi lease 1 detik
            ok_a = await acquire_lease(conn, "test_writer", "proc_A", duration_seconds=1)
            assert ok_a is True

            # Process B mencoba mengakuisisi lease yang sama sebelum kedaluwarsa -> harus GAGAL
            ok_b = await acquire_lease(conn, "test_writer", "proc_B", duration_seconds=1)
            assert ok_b is False

            # Tunggu 1.2 detik agar lease kedaluwarsa
            await asyncio.sleep(1.2)

            # Process B mencoba kembali setelah kedaluwarsa -> harus BERHASIL
            ok_b_retry = await acquire_lease(conn, "test_writer", "proc_B", duration_seconds=2)
            assert ok_b_retry is True

            # Process B renew lease
            renew_ok = await renew_lease(conn, "test_writer", "proc_B", duration_seconds=5)
            assert renew_ok is True

            # Process B melepaskan lease
            rel_ok = await release_lease(conn, "test_writer", "proc_B")
            assert rel_ok is True
    finally:
        _safe_remove(db_path)


@pytest.mark.asyncio
async def test_readonly_connection_pool():
    """Uji bahwa ReadonlyConnectionPool mengaktifkan query_only=ON dan melayani pembacaan."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async with get_db_connection(db_path) as conn:
            await execute_ddl_migrations(conn)

        pool = ReadonlyConnectionPool(db_path=db_path, max_connections=3)
        await pool.initialize()

        async with pool.acquire() as r_conn:
            cur = await r_conn.execute("PRAGMA query_only;")
            row = await cur.fetchone()
            assert row[0] == 1

            # Pembacaan diizinkan
            cur = await r_conn.execute("SELECT COUNT(*) FROM corporate_roles;")
            assert (await cur.fetchone())[0] == 0

            # Penulisan harus ditolak oleh SQLite karena query_only = ON
            with pytest.raises(Exception):
                await r_conn.execute("INSERT INTO system_settings VALUES ('k', 'v', 'c', datetime('now'));")

        await pool.close()
    finally:
        _safe_remove(db_path)


@pytest.mark.asyncio
async def test_quarantine_store_and_preflight():
    """Uji pengisolasian data korup ke quarantine_store dan preflight check."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async with get_db_connection(db_path) as conn:
            await execute_ddl_migrations(conn)

            qid = await quarantine_record(
                conn,
                source_table="corporate_messages",
                corrupted_payload={"bad_json": "corrupt_data_test"},
                error_reason="JSONDecodeError on payload chunk",
            )
            assert qid.startswith("qr_")

            cur = await conn.execute("SELECT * FROM quarantine_store WHERE id = ?", (qid,))
            row = await cur.fetchone()
            assert row is not None
            assert "corrupt_data_test" in row["corrupted_payload_json"]

            # Run preflight check
            ok = await run_db_preflight_check(conn, db_path)
            assert ok is True
    finally:
        _safe_remove(db_path)
