"""
Phase 1: Turn Preflight Inspector.
Menegakkan Invarian Suci 1 & 9:
- Cek status 1-klik Hold Ticket: jika status ON_HOLD atau interrupt_event aktif,
  iterasi berhenti seketika (0 token terbuang).
- Cek batas perulangan turn & kuota token.
"""

from typing import Any, Dict, Optional, Tuple
import aiosqlite

from app.core.logger import logger
from app.db.repos.ticket_repo import get_ticket


class PreflightResult:
    """Hasil verifikasi pre-flight sebelum memulai giliran agen."""

    def __init__(
        self,
        can_proceed: bool,
        status: str,
        ticket: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.can_proceed = can_proceed
        self.status = status  # 'READY' | 'ON_HOLD' | 'BLOCKED_LOOP' | 'BUDGET_EXCEEDED'
        self.ticket = ticket
        self.reason = reason


async def execute_turn_preflight(
    conn: aiosqlite.Connection,
    ticket_id: str,
    turn_count: int = 1,
    max_turns: int = 10,
    interrupt_flag: bool = False,
) -> PreflightResult:
    """Menjalankan pengecekan pre-flight deterministik sebelum memanggil API model."""
    # 1. Cek bendera interupsi memori
    if interrupt_flag:
        logger.info(f"[Preflight] Tiket [{ticket_id}] diinterupsi oleh Founder! Menghentikan eksekusi (0 Token).")
        return PreflightResult(
            can_proceed=False,
            status="ON_HOLD",
            reason="Interupsi manual aktif dari Founder.",
        )

    # 2. Ambil tiket dari database
    ticket = await get_ticket(conn, ticket_id)
    if not ticket:
        return PreflightResult(
            can_proceed=False,
            status="NOT_FOUND",
            reason=f"Tiket dengan ID {ticket_id} tidak ditemukan di database.",
        )

    # 3. Cek apakah tiket sedang dibekukan (1-Klik Hold Ticket dari Screen-Share Pane)
    ticket_status = ticket.get("status", "BACKLOG")
    if ticket_status == "ON_HOLD":
        logger.info(f"[Preflight] Tiket [{ticket_id}] berstatus ON_HOLD di DB. Preflight berhenti bersih (0 Token).")
        return PreflightResult(
            can_proceed=False,
            status="ON_HOLD",
            ticket=ticket,
            reason="Tiket sedang dibekukan (ON_HOLD) oleh Founder.",
        )

    # 4. Cek apakah tiket sudah selesai atau diblokir
    if ticket_status in ("DONE", "BLOCKED", "BLOCKED_LOOP_DETECTED"):
        return PreflightResult(
            can_proceed=False,
            status=ticket_status,
            ticket=ticket,
            reason=f"Tiket berada pada status terminal: {ticket_status}",
        )

    # 5. Cek batas turn
    if turn_count > max_turns:
        logger.warning(f"[Preflight] Tiket [{ticket_id}] melampaui batas maksimal {max_turns} giliran.")
        return PreflightResult(
            can_proceed=False,
            status="EXCEEDED_MAX_TURNS",
            ticket=ticket,
            reason=f"Batas maksimal giliran ({max_turns}) tercapai.",
        )

    # Lolos preflight
    return PreflightResult(can_proceed=True, status="READY", ticket=ticket)
