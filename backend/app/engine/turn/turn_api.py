"""
Phase 3 & 4: Turn API Invocation & Reasoning Extraction.
Menjalankan panggilan model ke SovereignModelRouter dengan watchdog liveness,
dan memancarkan pemikiran agen (reasoning tokens) ke feed Oasis corporate_messages.
"""

import asyncio
from typing import Any, Dict, Optional
import aiosqlite

from app.core.logger import logger
from app.db.repos.message_repo import insert_message
from app.gateway.model_router import SovereignModelRouter


async def execute_turn_api_call(
    conn: aiosqlite.Connection,
    router: SovereignModelRouter,
    project_id: str,
    ticket_id: str,
    role_id: str,
    system_prompt: str,
    user_prompt: str,
    primary_provider: str = "anthropic",
    primary_model: str = "claude-3-7-sonnet",
    fallback_models: Optional[list] = None,
    timeout_seconds: float = 60.0,
) -> Dict[str, Any]:
    """Menjalankan pemanggilan API model dengan pengawal timeout (watchdog)."""
    logger.info(f"[TurnAPI] Memanggil model untuk peran [{role_id}] pada tiket [{ticket_id}]...")

    try:
        completion_result = await asyncio.wait_for(
            router.execute_routed_completion(
                prompt=user_prompt,
                system_prompt=system_prompt,
                primary_provider=primary_provider,
                primary_model=primary_model,
                fallback_models=fallback_models,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"Pemanggilan model melampaui batas waktu {timeout_seconds} detik.")

    # Ekstraksi pemikiran (reasoning)
    reasoning = completion_result.get("reasoning", "")
    if reasoning:
        # Pancarkan ke corporate_messages (Oasis Live Stream Feed)
        await insert_message(
            conn,
            project_id=project_id,
            stream_category="GENERAL_THOUGHT",
            event_type="THOUGHT",
            content=reasoning,
            sender_role_id=role_id,
            metadata={"ticket_id": ticket_id, "model": completion_result.get("model")},
        )

    return completion_result
