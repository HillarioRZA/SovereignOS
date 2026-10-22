"""
Phase 10: Turn Finalizer, Telemetry Commit, & State Persistence.
Menyimpan metrik penggunaan token dan biaya ke corporate_token_ledger,
memperbarui status tiket, dan memancarkan telemetri ke Screen-Share Pane.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional
import uuid
import aiosqlite

from app.core.logger import logger
from app.db.repos.message_repo import insert_message
from app.db.repos.ticket_repo import update_screenshare_telemetry


async def finalize_turn_state(
    conn: aiosqlite.Connection,
    project_id: str,
    ticket_id: str,
    role_id: str,
    completion_metadata: Dict[str, Any],
    system_prompt_digest: str,
    tool_schema_digest: str,
    status_bubble: str = "Tugas giliran selesai.",
    scratchpad_note: str = "",
    is_completed: bool = False,
    is_loop_blocked: bool = False,
) -> Dict[str, Any]:
    """Menyimpan seluruh telemetri turn ke database secara atomik."""
    now_str = datetime.now(timezone.utc).isoformat()
    
    prompt_tokens = completion_metadata.get("prompt_tokens", 0)
    cached_tokens = completion_metadata.get("cached_prompt_tokens", 0)
    completion_tokens = completion_metadata.get("completion_tokens", 0)
    cost_usd = completion_metadata.get("cost_usd", 0.0)
    model_name = completion_metadata.get("model", "unknown")
    provider = completion_metadata.get("provider", "unknown")

    # 1. Catat ke corporate_token_ledger
    ledger_id = f"led_{uuid.uuid4().hex[:12]}"
    await conn.execute(
        """
        INSERT INTO corporate_token_ledger (
            id, project_id, ticket_id, role_id, model_provider, model_name,
            system_prompt_digest, tool_schema_digest, prompt_tokens,
            cached_prompt_tokens, completion_tokens, cost_usd, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ledger_id, project_id, ticket_id, role_id, provider, model_name,
            system_prompt_digest, tool_schema_digest, prompt_tokens,
            cached_tokens, completion_tokens, cost_usd, now_str,
        ),
    )

    # 2. Perbarui status dan biaya kumulatif tiket
    new_status = "BLOCKED_LOOP_DETECTED" if is_loop_blocked else ("DONE" if is_completed else "IN_PROGRESS")
    
    await conn.execute(
        """
        UPDATE corporate_tickets
        SET spent_tokens = spent_tokens + ?,
            spent_cost_usd = spent_cost_usd + ?,
            consultation_turns = consultation_turns + 1,
            status = CASE WHEN status = 'ON_HOLD' THEN 'ON_HOLD' ELSE ? END,
            updated_at = ?
        WHERE id = ?
        """,
        (prompt_tokens + completion_tokens, cost_usd, new_status, now_str, ticket_id),
    )

    # 3. Perbarui telemetry screen-share
    await update_screenshare_telemetry(
        conn,
        ticket_id=ticket_id,
        live_scratchpad_text=scratchpad_note,
        status_bubble_text=status_bubble,
    )

    await conn.commit()
    logger.info(
        f"[TurnFinalizer] Sukses komit turn. Biaya: ${cost_usd:.5f} | "
        f"Tokens: {prompt_tokens}+{completion_tokens} (Cached: {cached_tokens}) -> Status: {new_status}"
    )

    return {
        "ledger_id": ledger_id,
        "new_status": new_status,
        "spent_cost_usd": cost_usd,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
    }
