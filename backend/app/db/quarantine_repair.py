"""
Sidecar WAL Identity Guard & Quarantine Store Recovery.
Mendeteksi kerusakan berkas WAL/SHM saat preflight, mengisolasi data korup ke quarantine_store,
dan merekonstruksi indeks virtual FTS5 tanpa fatal crash.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import uuid
import aiosqlite

from app.core.logger import logger


def inspect_wal_files(db_path: str) -> Dict[str, Any]:
    """Memeriksa keberadaan dan ukuran file database utama, WAL, dan SHM."""
    main_p = Path(db_path)
    wal_p = Path(f"{db_path}-wal")
    shm_p = Path(f"{db_path}-shm")

    stats = {
        "main_exists": main_p.exists(),
        "main_size_bytes": main_p.stat().st_size if main_p.exists() else 0,
        "wal_exists": wal_p.exists(),
        "wal_size_bytes": wal_p.stat().st_size if wal_p.exists() else 0,
        "shm_exists": shm_p.exists(),
        "shm_size_bytes": shm_p.stat().st_size if shm_p.exists() else 0,
    }
    return stats


async def quarantine_record(
    conn: aiosqlite.Connection,
    source_table: str,
    corrupted_payload: Any,
    error_reason: str,
) -> str:
    """Mengisolasi payload atau baris bermasalah ke tabel quarantine_store."""
    qid = f"qr_{uuid.uuid4().hex[:12]}"
    payload_str = (
        json.dumps(corrupted_payload, default=str)
        if not isinstance(corrupted_payload, str)
        else corrupted_payload
    )
    now_str = datetime.now(timezone.utc).isoformat()

    await conn.execute(
        """
        INSERT INTO quarantine_store (id, source_table, corrupted_payload_json, error_reason, quarantined_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (qid, source_table, payload_str, error_reason, now_str),
    )
    await conn.commit()
    logger.warning(
        f"Data dari tabel [{source_table}] berhasil dikarantina ke ID [{qid}]. Alasan: {error_reason}"
    )
    return qid


async def rebuild_fts_indexes(conn: aiosqlite.Connection) -> None:
    """Membangun ulang indeks pencarian teks virtual FTS5 secara aman."""
    # corporate_skills_fts
    try:
        await conn.execute("INSERT INTO corporate_skills_fts(corporate_skills_fts) VALUES('rebuild');")
        logger.info("Indeks FTS5 'corporate_skills_fts' berhasil direkonstruksi.")
    except Exception as e:
        logger.debug(f"Lewati rebuild corporate_skills_fts (mungkin tabel belum ada): {e}")

    # messages_fts
    try:
        await conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild');")
        logger.info("Indeks FTS5 'messages_fts' berhasil direkonstruksi.")
    except Exception as e:
        logger.debug(f"Lewati rebuild messages_fts: {e}")


async def run_db_preflight_check(conn: aiosqlite.Connection, db_path: str) -> bool:
    """Menjalankan pemeriksaan integritas menyeluruh sebelum sistem menerima trafik agen."""
    logger.info(f"Menjalankan DB Preflight Check pada {db_path}...")
    try:
        cur = await conn.execute("PRAGMA quick_check;")
        res = await cur.fetchone()
        status = res[0] if res else "unknown"
        if status != "ok":
            logger.error(f"Peringatan PRAGMA quick_check mendeteksi anomali: {status}")
            # Coba PRAGMA integrity_check penuh
            full_cur = await conn.execute("PRAGMA integrity_check(5);")
            issues = await full_cur.fetchall()
            for issue in issues:
                await quarantine_record(
                    conn,
                    source_table="sqlite_master",
                    corrupted_payload={"diagnostic": issue[0]},
                    error_reason=f"Integrity check failure: {issue[0]}",
                )
            await rebuild_fts_indexes(conn)
            return False

        logger.info("DB Preflight Check: Integritas basis data SQLite WAL 100% OK.")
        return True
    except Exception as err:
        logger.error(f"DB Preflight Check mengalami kegagalan eksekusi: {err}")
        return False
