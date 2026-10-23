"""
Autonomous Kanban Swarm Runner Subsystem.
Menegakkan Topologi 3-Tier Flat Matrix:
- Tier 1: Executive Brain Trust merumuskan tiket DAG.
- Tier 2: Functional Talent Pools mengklaim tiket READY secara atomik dengan heartbeat lease.
- Tier 3: Independent Gatekeepers mengaudit sebelum PR disetujui.
"""

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Set
import aiosqlite

from app.core.logger import logger
from app.db.repos.ticket_repo import claim_ready_ticket, complete_ticket, get_ticket
from app.engine.orchestrator.event_bus import corporate_event_bus
from app.engine.roles.dynamic_node import DynamicNode
from app.engine.turn.turn_preflight import is_ticket_interrupted


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutonomousKanbanSwarm:
    """Runner kawanan agen otonom berbasis klaim tiket atomik dan heartbeat lease."""

    def __init__(self, max_concurrency: int = 5) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.active_ticket_ids: Set[str] = set()

    async def scan_and_claim_tickets(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        lease_duration_seconds: int = 30,
    ) -> List[Dict[str, Any]]:
        """Memindai seluruh tiket READY dan mengklaimnya secara atomik per peran yang ditugaskan."""
        # 1. Cari seluruh peran yang memiliki tiket READY atau lease kedaluwarsa
        cur = await conn.execute(
            """
            SELECT DISTINCT assigned_role_id FROM corporate_tickets
            WHERE project_id = ? AND (status = 'READY' OR (status = 'IN_PROGRESS' AND lease_expires_at < ?))
            """,
            (project_id, _now_iso()),
        )
        rows = await cur.fetchall()
        role_ids = [r["assigned_role_id"] for r in rows]

        claimed_tickets: List[Dict[str, Any]] = []
        for r_id in role_ids:
            claimed = await claim_ready_ticket(
                conn=conn,
                project_id=project_id,
                worker_role_id=r_id,
                lease_duration_seconds=lease_duration_seconds,
            )
            if claimed:
                claimed_tickets.append(claimed)
                await corporate_event_bus.publish(
                    conn=conn,
                    project_id=project_id,
                    stream_category="EXECUTION_HANDOFFS",
                    event_type="TASK_CLAIMED",
                    content=f"Tiket [{claimed['id']}] '{claimed['title']}' diklaim oleh {r_id}.",
                    sender_role_id=r_id,
                    metadata={"ticket_id": claimed["id"]},
                )

        logger.info(f"[KanbanSwarm] Mengklaim {len(claimed_tickets)} tiket untuk proyek [{project_id}].")
        return claimed_tickets

    async def check_and_update_dependencies(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
    ) -> int:
        """Memeriksa tiket berstatus BACKLOG; jika seluruh dependensinya DONE, ubah status menjadi READY."""
        cur = await conn.execute(
            "SELECT id, dependencies_json, assigned_role_id, title FROM corporate_tickets WHERE project_id = ? AND status = 'BACKLOG'",
            (project_id,),
        )
        backlog_tickets = await cur.fetchall()
        unblocked_count = 0
        now_str = _now_iso()

        for t in backlog_tickets:
            t_id = t["id"]
            deps: List[str] = json.loads(t["dependencies_json"] or "[]")
            if not deps:
                # Tanpa dependensi: langsung READY
                all_done = True
            else:
                # Cek apakah semua dependensi sudah berstatus DONE
                placeholders = ",".join(["?"] * len(deps))
                check_cur = await conn.execute(
                    f"SELECT COUNT(*) as done_count FROM corporate_tickets WHERE id IN ({placeholders}) AND status = 'DONE'",
                    deps,
                )
                done_row = await check_cur.fetchone()
                all_done = (done_row["done_count"] == len(deps)) if done_row else False

            if all_done:
                await conn.execute(
                    "UPDATE corporate_tickets SET status = 'READY', updated_at = ? WHERE id = ?",
                    (now_str, t_id),
                )
                unblocked_count += 1
                await corporate_event_bus.publish(
                    conn=conn,
                    project_id=project_id,
                    stream_category="EXECUTION_HANDOFFS",
                    event_type="TASK_READY",
                    content=f"Tiket [{t_id}] '{t['title']}' prasyaratnya terpenuhi -> status READY.",
                    sender_role_id=t["assigned_role_id"],
                    metadata={"ticket_id": t_id},
                )

        if unblocked_count > 0:
            await conn.commit()
            logger.info(f"[KanbanSwarm] Membuka {unblocked_count} tiket yang siap jalan (READY) di proyek [{project_id}].")

        return unblocked_count

    async def reclaim_expired_leases(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
    ) -> int:
        """Menarik kembali tiket IN_PROGRESS yang ditinggalkan worker (lease kedaluwarsa) menjadi READY."""
        now_str = _now_iso()
        cur = await conn.execute(
            """
            UPDATE corporate_tickets 
            SET status = 'READY', lease_owner = NULL, lease_expires_at = NULL, updated_at = ?
            WHERE project_id = ? AND status = 'IN_PROGRESS' AND lease_expires_at < ?
            """,
            (now_str, project_id, now_str),
        )
        await conn.commit()
        reclaimed = cur.rowcount
        if reclaimed > 0:
            logger.warning(f"[KanbanSwarm] Berhasil mereklamasi {reclaimed} tiket kedaluwarsa di proyek [{project_id}].")
        return reclaimed

    async def execute_claimed_ticket(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        ticket_id: str,
        role_id: str,
    ) -> bool:
        """Mengeksekusi satu tiket secara mandiri menggunakan DynamicNode dan Turn Loop."""
        if is_ticket_interrupted(ticket_id):
            logger.info(f"[KanbanSwarm] Eksekusi tiket [{ticket_id}] dibatalkan karena bendera ON_HOLD aktif.")
            return False

        async with self.semaphore:
            self.active_ticket_ids.add(ticket_id)
            try:
                node = await DynamicNode.from_role_id(conn, role_id)
                if not node:
                    logger.error(f"[KanbanSwarm] Peran [{role_id}] tidak ditemukan di database.")
                    return False

                result = await node.execute_turn(conn, project_id, ticket_id)
                if result.completed:
                    await complete_ticket(conn, ticket_id)
                    logger.info(f"[KanbanSwarm] Tiket [{ticket_id}] berhasil diselesaikan -> DONE.")
                    return True
                return False
            finally:
                self.active_ticket_ids.discard(ticket_id)


kanban_swarm = AutonomousKanbanSwarm()
