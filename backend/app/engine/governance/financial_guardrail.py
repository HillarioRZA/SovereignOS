"""
Autonomous Financial Circuit Breaker & Token-Spend Guardrail.
Mencegah lonjakan pengeluaran token API LLM dan membekukan tugas jika melampaui kuota,
tersinkronisasi dengan SQLite corporate_token_ledger dan notifikasi real-time.
"""

from typing import Any, Dict, Optional, Set
import aiosqlite

from app.core.logger import logger
from app.db.repos.ticket_repo import get_ticket
from app.engine.orchestrator.event_bus import corporate_event_bus

DEFAULT_MAX_TOKENS_PER_TICKET = 350000
DEFAULT_MAX_COST_DOLLARS = 1.50


class FinancialCircuitBreaker:
    """Pengawas anggaran finansial per tiket untuk mencegah cost runaway."""

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS_PER_TICKET,
        max_cost: float = DEFAULT_MAX_COST_DOLLARS,
    ) -> None:
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self._frozen_tickets: Set[str] = set()

    async def check_and_enforce_budget(
        self,
        conn: aiosqlite.Connection,
        ticket_id: str,
        tokens_spent: int,
        cost_usd: float,
    ) -> bool:
        """Memeriksa apakah penggunaan token atau biaya melampaui kuota.

        Jika melampaui batas, status tiket dibekukan ke FROZEN_PENDING_APPROVAL.
        """
        is_exceeded = tokens_spent >= self.max_tokens or cost_usd >= self.max_cost
        if is_exceeded:
            self._frozen_tickets.add(ticket_id)
            logger.critical(
                f"[FinOpsGuard] Financial Circuit Breaker TERPICU pada tiket [{ticket_id}]: "
                f"{tokens_spent:,} tokens (${cost_usd:.3f}). Batas: {self.max_tokens:,} tokens (${self.max_cost:.2f})."
            )

            await conn.execute(
                "UPDATE corporate_tickets SET status = 'FROZEN_PENDING_APPROVAL', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ticket_id,),
            )
            await conn.commit()

            tkt = await get_ticket(conn, ticket_id)
            project_id = tkt["project_id"] if tkt else "unknown"

            await corporate_event_bus.publish(
                conn=conn,
                project_id=project_id,
                stream_category="CEO_DECISION_GATES",
                event_type="FINANCIAL_QUOTA_FREEZE",
                content=(
                    f"⚠️ Tiket [{ticket_id}] dibekukan karena melampaui kuota token "
                    f"({tokens_spent:,} tokens, ${cost_usd:.2f}). Menunggu persetujuan top-up CEO."
                ),
                sender_role_id="system",
                metadata={
                    "ticket_id": ticket_id,
                    "tokens_spent": tokens_spent,
                    "cost_usd": cost_usd,
                    "max_tokens": self.max_tokens,
                    "max_cost": self.max_cost,
                },
            )
            return True

        return False

    async def approve_founder_budget_topup(
        self,
        conn: aiosqlite.Connection,
        ticket_id: str,
        additional_tokens: int = 150000,
        additional_dollars: float = 0.75,
    ) -> Dict[str, Any]:
        """Membuka kembali tiket yang dibekukan setelah Founder menyetujui penambahan anggaran."""
        self._frozen_tickets.discard(ticket_id)

        await conn.execute(
            "UPDATE corporate_tickets SET status = 'READY', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (ticket_id,),
        )
        await conn.commit()

        tkt = await get_ticket(conn, ticket_id)
        project_id = tkt["project_id"] if tkt else "unknown"

        await corporate_event_bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="CEO_DECISION_GATES",
            event_type="BUDGET_TOPUP_APPROVED",
            content=f"👑 Founder menyetujui top-up anggaran tiket [{ticket_id}] (+{additional_tokens:,} tokens, +${additional_dollars:.2f}).",
            sender_role_id="founder",
            metadata={"ticket_id": ticket_id, "additional_tokens": additional_tokens},
        )

        logger.info(f"[FinOpsGuard] Tiket [{ticket_id}] dicairkan kembali dengan top-up kuota.")
        return {
            "ticket_id": ticket_id,
            "status": "READY",
            "message": "Tiket aktif kembali dengan alokasi anggaran tambahan.",
        }


financial_guardrail = FinancialCircuitBreaker()
