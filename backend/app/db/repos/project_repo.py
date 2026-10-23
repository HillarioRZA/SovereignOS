"""
Repository Proyek dan Runbook Korporat (projects & corporate_runbooks).
Menyediakan operasi persistensi untuk inisiasi proyek baru dan template alur kerja DAG.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_project(
    conn: aiosqlite.Connection,
    id: str,
    name: str,
    founder_vision: str,
    product_archetype: str,
    active_sandbox_profile: str = "profile-web-saas",
    active_runbook_id: Optional[str] = None,
    status: str = "DISCOVERY",
) -> Dict[str, Any]:
    """Mendaftarkan proyek venture baru ke basis data."""
    now_str = _now_iso()
    query = """
    INSERT INTO projects (
        id, name, founder_vision, product_archetype, 
        active_runbook_id, active_sandbox_profile, status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    RETURNING *;
    """
    cur = await conn.execute(
        query,
        (
            id,
            name,
            founder_vision,
            product_archetype,
            active_runbook_id,
            active_sandbox_profile,
            status,
            now_str,
        ),
    )
    row = await cur.fetchone()
    await conn.commit()
    return dict(row) if row else {}


async def get_project(conn: aiosqlite.Connection, project_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil metadata proyek berdasarkan ID."""
    cur = await conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def update_project_status(
    conn: aiosqlite.Connection, project_id: str, status: str
) -> bool:
    """Memperbarui fase status proyek."""
    cur = await conn.execute(
        "UPDATE projects SET status = ? WHERE id = ?", (status, project_id)
    )
    await conn.commit()
    return cur.rowcount > 0


async def create_runbook(
    conn: aiosqlite.Connection,
    id: str,
    name: str,
    description: str,
    dag_stages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mendaftarkan template alur kerja Runbook DAG baru."""
    now_str = _now_iso()
    dag_json = json.dumps(dag_stages)
    query = """
    INSERT INTO corporate_runbooks (id, name, description, dag_stages_json, created_at)
    VALUES (?, ?, ?, ?, ?)
    RETURNING *;
    """
    cur = await conn.execute(query, (id, name, description, dag_json, now_str))
    row = await cur.fetchone()
    await conn.commit()
    return dict(row) if row else {}


async def get_runbook(conn: aiosqlite.Connection, runbook_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil definisi alur kerja Runbook berdasarkan ID."""
    cur = await conn.execute("SELECT * FROM corporate_runbooks WHERE id = ?", (runbook_id,))
    row = await cur.fetchone()
    return dict(row) if row else None
