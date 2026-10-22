"""Entrypoint ASGI & lifespan initialization for Sovereign OS Control Plane."""
import sys
from pathlib import Path

# Memastikan direktori backend selalu terdaftar di sys.path
backend_dir = str(Path(__file__).resolve().parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI

from app.core.logger import logger
from app.db.bootstrap import bootstrap_database
from app.db.session import get_db_connection, close_pg_pool
from app.db.state_lease import StateLeaseDaemon
from app.db.read_pool import get_read_pool

lease_daemon: Optional[StateLeaseDaemon] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global lease_daemon
    logger.info("=== Sovereign OS Control Plane Starting Up ===")
    
    # 1. Deterministik Database Bootstrap & Catalog Ingest
    await bootstrap_database()

    # 2. Inisialisasi Read-Only Pool
    read_pool = await get_read_pool()

    # 3. Start Single-Writer State Lease Heartbeat Daemon
    lease_daemon = StateLeaseDaemon(lease_key="primary_gateway_writer")
    started = await lease_daemon.start(get_db_connection)
    if not started:
        logger.warning("Peringatan: Gagal mengakuisisi exclusive writer lease saat boot!")

    yield

    # Graceful shutdown sequence
    logger.info("=== Sovereign OS Control Plane Shutting Down ===")
    if lease_daemon:
        await lease_daemon.stop(get_db_connection)
    await read_pool.close()
    await close_pg_pool()


app = FastAPI(title="Sovereign OS", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def health_check():
    return {
        "status": "ok",
        "system": "Sovereign OS",
        "version": "0.1.0",
        "engine": "Dual-Engine SQLite WAL / asyncpg",
    }

