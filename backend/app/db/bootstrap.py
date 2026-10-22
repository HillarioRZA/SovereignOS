"""
Deterministik Bootstrap & Database Initializer.
Mengeksekusi DDL 28 tabel, memeriksa integritas WAL, mendaftarkan baseline tools,
dan melakukan auto-ingest katalog agen jika database baru.
"""

import asyncio
from typing import Dict
import aiosqlite

from app.core.config import settings
from app.core.logger import logger
from app.db.session import get_db_connection, resolve_db_path, init_pg_pool
from app.db.schemas import execute_ddl_migrations
from app.db.quarantine_repair import run_db_preflight_check
from app.engine.tools.permission_registry import seed_baseline_tools
from app.engine.roles.agency_loader import ingest_agents_catalog


async def bootstrap_database(custom_db_path: str = "") -> Dict[str, int]:
    """Menjalankan siklus bootstrap deterministik lengkap."""
    target_path = resolve_db_path(custom_db_path) if custom_db_path else resolve_db_path()
    logger.info(f"Memulai bootstrap database Sovereign OS pada: {target_path}")

    await init_pg_pool()

    async with get_db_connection(target_path) as conn:
        # 1. Eksekusi 28 Skema DDL
        ddl_count = await execute_ddl_migrations(conn)
        logger.info(f"[Bootstrap 1/4] {ddl_count} pernyataan DDL berhasil dieksekusi.")

        # 2. Preflight quick_check & FTS5 integrity
        await run_db_preflight_check(conn, target_path)
        logger.info("[Bootstrap 2/4] DB Preflight Quick Check selesai.")

        # 3. Pendaftaran Baseline RBAC Tools
        tools_count = await seed_baseline_tools(conn)
        logger.info(f"[Bootstrap 3/4] {tools_count} perkakas dasar terdaftar.")

        # 4. Ingesti Katalog Agen jika roles masih kosong
        cur = await conn.execute("SELECT COUNT(*) as count FROM corporate_roles")
        row = await cur.fetchone()
        roles_count = row["count"] if row else 0

        ingest_stats = {"divisions": 0, "runbooks": 0, "roles": roles_count}
        if roles_count == 0:
            logger.info("[Bootstrap 4/4] Tabel corporate_roles kosong. Memulai auto-ingest dari catalog/...")
            ingest_stats = await ingest_agents_catalog(conn)
        else:
            logger.info(f"[Bootstrap 4/4] {roles_count} peran telah tersedia di database. Lewati ingesti ulang.")

    logger.info("Bootstrap basis data Sovereign OS selesai 100% dengan sukses!")
    return {
        "ddl_statements": ddl_count,
        "tools_registered": tools_count,
        "divisions": ingest_stats["divisions"],
        "roles": ingest_stats["roles"],
    }


if __name__ == "__main__":
    asyncio.run(bootstrap_database())
