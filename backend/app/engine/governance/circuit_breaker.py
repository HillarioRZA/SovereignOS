"""
Agent Interaction Circuit Breaker & Anti-Infinite Loop Guardrail.
Menegakkan Invarian Suci 10:
Mendeteksi dan menghentikan perulangan perdebatan tak berujung (discussion loops >= 3 turns)
antar-agen secara otomatis, serta menyediakan mekanisme manual override bagi CEO.
"""

from typing import Any, Dict, Optional, Set
import aiosqlite

from app.core.logger import logger
from app.db.repos.ticket_repo import get_ticket
from app.engine.orchestrator.event_bus import corporate_event_bus

MAX_CONSECUTIVE_TURNS = 3


class AgentCircuitBreaker:
    """Pengawas anti-infinite loop antar-agen pada level tiket tugas."""

    def __init__(self, max_turns: int = MAX_CONSECUTIVE_TURNS) -> None:
        self.max_turns = max_turns
        self._turn_counters: Dict[str, int] = {}
        self._blocked_tickets: Set[str] = set()

    async def record_consultation_turn(
        self,
        conn: aiosqlite.Connection,
        ticket_id: str,
        sender_role: str,
        recipient_role: str,
        topic_summary: str,
    ) -> bool:
        """Mencatat satu giliran diskusi antar-agen pada tiket.

        Jika mencapai batas (>= 3 putaran), tugas dibekukan ke BLOCKED_LOOP_DETECTED.
        """
        current_count = self._turn_counters.get(ticket_id, 0) + 1
        self._turn_counters[ticket_id] = current_count
        logger.info(f"[CircuitBreaker] Tiket [{ticket_id}] turn {current_count}/{self.max_turns}")

        if current_count >= self.max_turns:
            self._blocked_tickets.add(ticket_id)
            warning_msg = (
                f"⚠️ Circuit Breaker Terpicu: Diskusi antara [{sender_role}] dan [{recipient_role}] "
                f"telah mencapai {current_count} putaran tanpa artefak baru ({topic_summary}). "
                f"Tugas otomatis DIBEKUKAN (BLOCKED_LOOP_DETECTED) menunggu intervensi CEO."
            )
            logger.warning(warning_msg)

            # Update status tiket di database
            await conn.execute(
                "UPDATE corporate_tickets SET status = 'BLOCKED_LOOP_DETECTED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ticket_id,),
            )
            await conn.commit()

            tkt = await get_ticket(conn, ticket_id)
            project_id = tkt["project_id"] if tkt else "unknown"

            # Siarkan peringatan ke stream CEO_DECISION_GATES
            await corporate_event_bus.publish(
                conn=conn,
                project_id=project_id,
                stream_category="CEO_DECISION_GATES",
                event_type="CIRCUIT_BREAKER_TRIGGERED",
                content=warning_msg,
                sender_role_id="system",
                metadata={"ticket_id": ticket_id, "turns": current_count},
            )
            return True

        return False

    def reset_counter(self, ticket_id: str) -> None:
        """Mereset counter giliran ketika ada kemajuan kode baru."""
        self._turn_counters.pop(ticket_id, None)
        self._blocked_tickets.discard(ticket_id)

    async def execute_ceo_override(
        self,
        conn: aiosqlite.Connection,
        ticket_id: str,
        action: str,
        directive: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mengeksekusi intervensi hak veto CEO terhadap tiket yang terblokir."""
        self.reset_counter(ticket_id)
        logger.info(f"[CircuitBreaker] CEO Manual Override pada [{ticket_id}]: {action}")

        if action == "FORCE_PROCEED":
            new_status = "DONE"
            msg = f"👑 CEO Manual Override: Tiket [{ticket_id}] dipaksa selesai (FORCE_PROCEED -> DONE)."
        elif action == "REASSIGN":
            new_status = "READY"
            msg = f"👑 CEO Manual Override: Tiket [{ticket_id}] dialihkan kembali ke talent pool (READY)."
        else:  # INTERVENE
            new_status = "IN_PROGRESS"
            msg = f"👑 CEO Intervensi: Tiket [{ticket_id}] dilanjutkan dengan arahan: '{directive}'."

        await conn.execute(
            "UPDATE corporate_tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, ticket_id),
        )
        await conn.commit()

        tkt = await get_ticket(conn, ticket_id)
        project_id = tkt["project_id"] if tkt else "unknown"

        await corporate_event_bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="CEO_DECISION_GATES",
            event_type="CEO_INTERVENTION",
            content=msg,
            sender_role_id="founder",
            metadata={"ticket_id": ticket_id, "action": action, "directive": directive},
        )

        return {"ticket_id": ticket_id, "status": new_status, "action": action, "message": msg}


agent_circuit_breaker = AgentCircuitBreaker()
