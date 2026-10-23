"""
Dynamic Runbook DAG Engine.
Mengonversi grafik tahapan playbooks (Discovery s/d Operate) menjadi tiket-tiket
di papan Kanban virtual dengan resolusi relasi dependensi terarah.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Set
import aiosqlite

from app.core.logger import logger
from app.db.repos.project_repo import get_runbook
from app.db.repos.role_repo import get_role_by_handle


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunbookDAGEngine:
    """Mesin penyusun dan validator ketergantungan DAG alur kerja korporat."""

    def get_ready_stages(
        self, completed_stages: Set[str], dag_stages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Menyaring tahapan DAG yang seluruh prasyaratnya telah selesai."""
        ready = []
        for stage in dag_stages:
            stage_id = stage.get("id")
            if stage_id in completed_stages:
                continue
            deps = stage.get("dependencies", [])
            if all(dep in completed_stages for dep in deps):
                ready.append(stage)
        return ready

    async def compile_runbook_to_tickets(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        runbook_id: str,
    ) -> List[Dict[str, Any]]:
        """Membaca definisi DAG Runbook dan menginstansiasi tiket-tiket tugas di basis data."""
        runbook = await get_runbook(conn, runbook_id)
        if not runbook:
            raise ValueError(f"Runbook dengan ID '{runbook_id}' tidak ditemukan.")

        dag_stages: List[Dict[str, Any]] = json.loads(runbook.get("dag_stages_json", "[]"))
        created_tickets: List[Dict[str, Any]] = []
        now_str = _now_iso()

        for stage in dag_stages:
            stage_id = stage["id"]
            ticket_id = f"tkt_{project_id}_{stage_id}"
            handle = stage.get("assigned_role_handle", "@pm")

            # Resolusi ID peran dari handle
            role_data = await get_role_by_handle(conn, handle)
            if role_data:
                role_id = role_data["id"]
            else:
                # Fallback: cari sembarang peran default atau gunakan handle langsung
                logger.warning(f"[RunbookDAG] Role untuk {handle} tidak ditemukan, mencari fallback.")
                cur = await conn.execute("SELECT id FROM corporate_roles LIMIT 1")
                row = await cur.fetchone()
                role_id = row["id"] if row else "role_default"

            deps = stage.get("dependencies", [])
            ticket_deps = [f"tkt_{project_id}_{d}" for d in deps]

            # Akar DAG (tanpa dependensi) berstatus READY, sisanya BACKLOG
            initial_status = "READY" if not deps else "BACKLOG"
            priority = stage.get("priority", "HIGH" if not deps else "MEDIUM")
            title = stage.get("name", stage_id)
            desc = stage.get("description", f"Tahapan alur kerja: {title}")
            ac = stage.get("acceptance_criteria", "Deliverable memenuhi seluruh kriteria mutu.")

            query = """
            INSERT INTO corporate_tickets (
                id, project_id, assigned_role_id, title, description,
                acceptance_criteria, status, priority, dependencies_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING *;
            """
            cur = await conn.execute(
                query,
                (
                    ticket_id,
                    project_id,
                    role_id,
                    title,
                    desc,
                    ac,
                    initial_status,
                    priority,
                    json.dumps(ticket_deps),
                    now_str,
                ),
            )
            created_ticket = await cur.fetchone()
            if created_ticket:
                created_tickets.append(dict(created_ticket))

        await conn.commit()
        logger.info(
            f"[RunbookDAG] Berhasil mengompilasi runbook [{runbook_id}] menjadi "
            f"{len(created_tickets)} tiket untuk proyek [{project_id}]."
        )
        return created_tickets


runbook_dag_engine = RunbookDAGEngine()
