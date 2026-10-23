"""
Hierarchical Delegation Tree Subsystem.
Mengelola pendelegasian subtugas (delegate_task) dari agen senior ke spesialis bawahan.
Menjaga hierarki parent_ticket_id dan pemblokiran tiket induk hingga seluruh subtiket selesai.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import uuid
import aiosqlite

from app.core.logger import logger
from app.engine.orchestrator.event_bus import corporate_event_bus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DelegationTree:
    """Manajer pohon pendelegasian tugas hierarkis antar-agen."""

    async def delegate_subtask(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        parent_ticket_id: str,
        assigned_role_id: str,
        title: str,
        description: str,
        acceptance_criteria: str,
    ) -> Dict[str, Any]:
        """Mendelegasikan tugas bawahan yang terhubung langsung ke parent_ticket_id."""
        subtask_id = f"tkt_sub_{uuid.uuid4().hex[:8]}"
        now_str = _now_iso()

        query = """
        INSERT INTO corporate_tickets (
            id, project_id, parent_ticket_id, assigned_role_id,
            title, description, acceptance_criteria, status, priority,
            dependencies_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'READY', 'HIGH', '[]', ?)
        RETURNING *;
        """
        cur = await conn.execute(
            query,
            (
                subtask_id,
                project_id,
                parent_ticket_id,
                assigned_role_id,
                title,
                description,
                acceptance_criteria,
                now_str,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()
        created_subtask = dict(row) if row else {}

        await corporate_event_bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="EXECUTION_HANDOFFS",
            event_type="DELEGATION_CREATED",
            content=f"Subtugas [{subtask_id}] '{title}' didelegasikan dari [{parent_ticket_id}] ke {assigned_role_id}.",
            sender_role_id=assigned_role_id,
            metadata={"parent_ticket_id": parent_ticket_id, "subtask_id": subtask_id},
        )

        logger.info(f"[DelegationTree] Subtugas [{subtask_id}] sukses didelegasikan dari [{parent_ticket_id}].")
        return created_subtask

    async def check_subtasks_completed(
        self,
        conn: aiosqlite.Connection,
        parent_ticket_id: str,
    ) -> bool:
        """Memeriksa apakah seluruh subtiket milik tiket induk telah berstatus DONE."""
        cur = await conn.execute(
            "SELECT COUNT(*) as unfinished FROM corporate_tickets WHERE parent_ticket_id = ? AND status != 'DONE'",
            (parent_ticket_id,),
        )
        row = await cur.fetchone()
        unfinished = row["unfinished"] if row else 0
        return unfinished == 0

    async def get_delegation_children(
        self,
        conn: aiosqlite.Connection,
        parent_ticket_id: str,
    ) -> List[Dict[str, Any]]:
        """Mengambil seluruh daftar subtiket yang terdaftar di bawah tiket induk."""
        cur = await conn.execute(
            "SELECT * FROM corporate_tickets WHERE parent_ticket_id = ? ORDER BY created_at ASC",
            (parent_ticket_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


delegation_tree = DelegationTree()
