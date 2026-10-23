"""
Office Dispatch Subsystem.
Menangani aksi 1-klik Hold Ticket untuk membekukan tiket menjadi ON_HOLD,
memicu sinyal interupsi preflight (0 Token Terbuang), serta melepas kunci FileLockManager.
"""

from typing import Any, Dict, Optional
import aiosqlite

from app.core.logger import logger
from app.db.repos.ticket_repo import hold_ticket, resume_ticket, get_ticket
from app.engine.turn.turn_preflight import set_ticket_interrupted, clear_ticket_interrupted
from app.engine.orchestrator.file_lock_manager import file_lock_manager
from app.engine.orchestrator.event_bus import corporate_event_bus


class OfficeDispatch:
    """Dispatcher intervensi langsung Founder dari konsol /office."""

    async def hold_ticket_action(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        ticket_id: str,
    ) -> Dict[str, Any]:
        """Aksi 1-Klik Hold Ticket:

        1. Set bendera interupsi memori di turn_preflight agar turn loop berhenti seketika.
        2. Ubah status tiket di database menjadi ON_HOLD dan kosongkan lease.
        3. Lepaskan seluruh kunci file aktif di FileLockManager untuk mencegah deadlock.
        4. Siarkan notifikasi ke stream CEO_DECISION_GATES.
        """
        logger.info(f"[OfficeDispatch] Founder memicu 1-Klik Hold Ticket pada [{ticket_id}]")

        # 1. Memicu sinyal interupsi memori
        set_ticket_interrupted(ticket_id)

        # 2. Update DB
        success = await hold_ticket(conn, ticket_id)
        if not success:
            logger.warning(f"[OfficeDispatch] Gagal memperbarui status ON_HOLD pada tiket [{ticket_id}].")

        # 3. Lepaskan kunci FileLockManager proyek
        released_locks = file_lock_manager.release_all_project_locks(project_id)

        # 4. Siarkan event ke bus
        await corporate_event_bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="CEO_DECISION_GATES",
            event_type="HOLD_TICKET",
            content=f"Tiket [{ticket_id}] dibekukan oleh Founder (ON_HOLD). {released_locks} kunci dilepas.",
            sender_role_id="founder",
            metadata={"ticket_id": ticket_id, "released_locks": released_locks},
        )

        return {
            "ticket_id": ticket_id,
            "status": "ON_HOLD",
            "message": "Tiket berhasil dibekukan (0 Token Overhead).",
            "released_locks": released_locks,
        }

    async def resume_ticket_action(
        self,
        conn: aiosqlite.Connection,
        ticket_id: str,
    ) -> Dict[str, Any]:
        """Mengaktifkan kembali tiket dari ON_HOLD menjadi READY."""
        logger.info(f"[OfficeDispatch] Founder mengaktifkan kembali tiket [{ticket_id}]")

        clear_ticket_interrupted(ticket_id)
        success = await resume_ticket(conn, ticket_id)

        tkt = await get_ticket(conn, ticket_id)
        project_id = tkt["project_id"] if tkt else "unknown"

        await corporate_event_bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="EXECUTION_HANDOFFS",
            event_type="TICKET_RESUMED",
            content=f"Tiket [{ticket_id}] telah dicairkan kembali menjadi READY.",
            sender_role_id="founder",
            metadata={"ticket_id": ticket_id},
        )

        return {
            "ticket_id": ticket_id,
            "status": "READY",
            "message": "Tiket siap diklaim kembali oleh talent pool.",
        }


office_dispatch = OfficeDispatch()
