"""
Repository Tiket Kanban Swarm (corporate_tickets).
Menyediakan operasi claim atomik, aksi 1-klik Hold Ticket, dan telemetri screen-share.
"""

from datetime import datetime, timezone, timedelta
import json
from typing import Any, Dict, List, Optional
import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


async def get_ticket(conn: aiosqlite.Connection, ticket_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil detail tiket berdasarkan ID."""
    cur = await conn.execute("SELECT * FROM corporate_tickets WHERE id = ?", (ticket_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def claim_ready_ticket(
    conn: aiosqlite.Connection,
    project_id: str,
    worker_role_id: str,
    lease_duration_seconds: int = 30,
) -> Optional[Dict[str, Any]]:
    """Klaim tiket secara atomik dengan status READY menjadi IN_PROGRESS beserta heartbeat lease."""
    now_str = _now_iso()
    exp_str = _future_iso(lease_duration_seconds)

    # Subquery atomik untuk mengambil 1 tiket READY dengan prioritas tertinggi
    query = """
    UPDATE corporate_tickets
    SET status = 'IN_PROGRESS',
        lease_owner = ?,
        lease_expires_at = ?,
        updated_at = ?
    WHERE id = (
        SELECT id FROM corporate_tickets
        WHERE project_id = ? 
          AND assigned_role_id = ?
          AND (status = 'READY' OR (status = 'IN_PROGRESS' AND lease_expires_at < ?))
        ORDER BY 
            CASE priority 
                WHEN 'CRITICAL' THEN 1 
                WHEN 'HIGH' THEN 2 
                WHEN 'MEDIUM' THEN 3 
                ELSE 4 
            END ASC,
            updated_at ASC
        LIMIT 1
    )
    RETURNING *;
    """
    cur = await conn.execute(
        query,
        (worker_role_id, exp_str, now_str, project_id, worker_role_id, now_str),
    )
    row = await cur.fetchone()
    await conn.commit()
    return dict(row) if row else None


async def hold_ticket(conn: aiosqlite.Connection, ticket_id: str) -> bool:
    """Aksi 1-klik Hold Ticket: membekukan status menjadi ON_HOLD dan melepaskan lease."""
    now_str = _now_iso()
    cur = await conn.execute(
        """
        UPDATE corporate_tickets
        SET status = 'ON_HOLD',
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (now_str, ticket_id),
    )
    await conn.commit()
    return cur.rowcount > 0


async def resume_ticket(conn: aiosqlite.Connection, ticket_id: str) -> bool:
    """Mengembalikan tiket dari ON_HOLD menjadi READY agar dapat diklaim kembali."""
    now_str = _now_iso()
    cur = await conn.execute(
        """
        UPDATE corporate_tickets
        SET status = 'READY',
            updated_at = ?
        WHERE id = ? AND status = 'ON_HOLD'
        """,
        (now_str, ticket_id),
    )
    await conn.commit()
    return cur.rowcount > 0


async def update_screenshare_telemetry(
    conn: aiosqlite.Connection,
    ticket_id: str,
    active_file_path: Optional[str] = None,
    live_scratchpad_text: Optional[str] = None,
    status_bubble_text: Optional[str] = None,
) -> None:
    """Memperbarui status berkas aktif dan scratchpad pemikiran secara real-time."""
    now_str = _now_iso()
    await conn.execute(
        """
        UPDATE corporate_tickets
        SET active_file_path = COALESCE(?, active_file_path),
            live_scratchpad_text = COALESCE(?, live_scratchpad_text),
            status_bubble_text = COALESCE(?, status_bubble_text),
            updated_at = ?
        WHERE id = ?
        """,
        (active_file_path, live_scratchpad_text, status_bubble_text, now_str, ticket_id),
    )
    await conn.commit()


async def complete_ticket(
    conn: aiosqlite.Connection,
    ticket_id: str,
    artifact_refs: Optional[List[str]] = None,
) -> bool:
    """Menandai tiket selesai (DONE)."""
    now_str = _now_iso()
    artifacts_json = json.dumps(artifact_refs or [])
    cur = await conn.execute(
        """
        UPDATE corporate_tickets
        SET status = 'DONE',
            artifact_refs_json = ?,
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (artifacts_json, now_str, ticket_id),
    )
    await conn.commit()
    return cur.rowcount > 0
