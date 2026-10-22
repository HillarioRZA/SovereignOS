"""
Turn Facade: Titik Masuk Utama 10-Phase Turn Loop Engine.
Pola Facade + Siblings Hermes: Mengorkestrasi seluruh 10 fase giliran agen secara deterministik.
"""

from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.logger import logger
from app.engine.governance.cov_verifier import CoVVerifier
from app.engine.tools.mock_executor import MockToolExecutor
from app.engine.turn.turn_preflight import execute_turn_preflight, PreflightResult
from app.engine.turn.turn_request import assemble_turn_request
from app.engine.turn.turn_api import execute_turn_api_call
from app.engine.turn.turn_tool_round import execute_turn_tool_round
from app.engine.turn.turn_compaction import check_turn_loop_circuit_breaker
from app.engine.turn.turn_finalizer import finalize_turn_state
from app.gateway.model_router import SovereignModelRouter


class TurnCycleResult:
    """Hasil akhir dari eksekusi 1 siklus giliran agen."""

    def __init__(
        self,
        success: bool,
        status: str,
        content: str = "",
        reasoning: str = "",
        tool_results: Optional[List[Dict[str, Any]]] = None,
        cost_usd: float = 0.0,
        tokens_used: int = 0,
        message: str = "",
    ) -> None:
        self.success = success
        self.status = status
        self.content = content
        self.reasoning = reasoning
        self.tool_results = tool_results or []
        self.cost_usd = cost_usd
        self.tokens_used = tokens_used
        self.message = message


async def run_turn_cycle(
    conn: aiosqlite.Connection,
    project_id: str,
    ticket_id: str,
    role_id: str,
    router: Optional[SovereignModelRouter] = None,
    cov_verifier: Optional[CoVVerifier] = None,
    tool_executor: Optional[MockToolExecutor] = None,
    turn_count: int = 1,
    consecutive_empty_turns: int = 0,
    interrupt_flag: bool = False,
    simulate_critic_pass: bool = False,
) -> TurnCycleResult:
    """Menjalankan 1 siklus penuh 10-Phase Turn Loop."""
    active_router = router or SovereignModelRouter()
    active_verifier = cov_verifier or CoVVerifier(router=active_router)
    active_executor = tool_executor or MockToolExecutor()

    # 1. PHASE 1: PREFLIGHT
    preflight: PreflightResult = await execute_turn_preflight(
        conn=conn,
        ticket_id=ticket_id,
        turn_count=turn_count,
        interrupt_flag=interrupt_flag,
    )
    if not preflight.can_proceed:
        return TurnCycleResult(
            success=False,
            status=preflight.status,
            message=preflight.reason or "Preflight menolak eksekusi.",
        )

    ticket = preflight.ticket or {}

    # 2. PHASE 2: REQUEST & CACHE BOUNDARY ASSEMBLY
    sys_prompt, user_prompt, sys_digest, tool_digest, sorted_tools, prov, mdl, fbs = await assemble_turn_request(
        conn=conn,
        project_id=project_id,
        ticket=ticket,
        role_id=role_id,
    )

    # 3. PHASE 3 & 4: API CALL & REASONING EXTRACTION
    completion_meta = await execute_turn_api_call(
        conn=conn,
        router=active_router,
        project_id=project_id,
        ticket_id=ticket_id,
        role_id=role_id,
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        primary_provider=prov,
        primary_model=mdl,
        fallback_models=fbs,
    )

    model_content = completion_meta.get("content", "")
    reasoning = completion_meta.get("reasoning", "")
    allowed_tool_ids = [t.get("name", t.get("tool_id")) for t in sorted_tools]

    # 4. PHASE 5, 6, 7 & 8: TOOL ROUND (RBAC, TWO-TIER COV, EXECUTION)
    tool_round_result = await execute_turn_tool_round(
        conn=conn,
        project_id=project_id,
        ticket_id=ticket_id,
        role_id=role_id,
        model_content=model_content,
        allowed_tool_ids=allowed_tool_ids,
        cov_verifier=active_verifier,
        tool_executor=active_executor,
        simulate_critic_pass=simulate_critic_pass,
    )

    tool_results = tool_round_result.get("tool_results", [])
    has_tools = tool_round_result.get("has_tool_calls", False)

    # 5. PHASE 9: CONTEXT COMPACTION & ANTI-LOOP CIRCUIT BREAKER
    new_empty_turns = 0 if has_tools else (consecutive_empty_turns + 1)
    is_loop, loop_msg = check_turn_loop_circuit_breaker(new_empty_turns)

    # Tentukan apakah tugas selesai jika tidak ada tool calls dan tidak ada loop
    is_completed = (not has_tools) and (not is_loop) and len(model_content) > 20

    # 6. PHASE 10: STATE FINALIZATION & TOKEN LEDGER COMMIT
    status_bubble = "Menjalankan perkakas..." if has_tools else "Menyelesaikan giliran."
    scratchpad = model_content[:200] if model_content else reasoning[:200]

    fin_meta = await finalize_turn_state(
        conn=conn,
        project_id=project_id,
        ticket_id=ticket_id,
        role_id=role_id,
        completion_metadata=completion_meta,
        system_prompt_digest=sys_digest,
        tool_schema_digest=tool_digest,
        status_bubble=status_bubble,
        scratchpad_note=scratchpad,
        is_completed=is_completed,
        is_loop_blocked=is_loop,
    )

    return TurnCycleResult(
        success=not is_loop,
        status=fin_meta.get("new_status", "IN_PROGRESS"),
        content=model_content,
        reasoning=reasoning,
        tool_results=tool_results,
        cost_usd=fin_meta.get("spent_cost_usd", 0.0),
        tokens_used=fin_meta.get("prompt_tokens", 0) + fin_meta.get("completion_tokens", 0),
        message=loop_msg or "Giliran selesai dengan sukses.",
    )
