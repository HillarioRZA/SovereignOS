"""
Phase 5, 6, 7 & 8: Tool Detection, RBAC Check, CoV (LLM / Jev), & Execution Round.
Menegakkan Invarian Suci 6, 7 & 8:
- RBAC Tools diverifikasi dinamis dari basis data.
- CoV Verifier dengan 2 Mode yang dapat dipilih: Full LLM Critic vs TypeSafe AI Jev.
- Otonomi Peran: Respon tanpa perkakas langsung dilempar/passthrough ke pengguna/agen lain.
- Non-Hijacking Worker Self-Repair: CoV hanya mengembalikan verdict & feedback; agen peran yang memperbaiki & mengeksekusi.
- Batas output maksimal tool 50KB.
"""

import json
from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.logger import logger
from app.db.repos.message_repo import insert_message
from app.engine.governance.cov_verifier import CoVVerifier, CoVInspectionResult
from app.engine.tools.mock_executor import MockToolExecutor
from app.engine.tools.permission_registry import check_role_has_tool_permission


async def execute_turn_tool_round(
    conn: aiosqlite.Connection,
    project_id: str,
    ticket_id: str,
    role_id: str,
    model_content: str,
    allowed_tool_ids: List[str],
    cov_verifier: Optional[CoVVerifier] = None,
    tool_executor: Optional[MockToolExecutor] = None,
    simulate_critic_pass: bool = False,
    tool_schemas: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Mengekstrak respon agen peran, memeriksa RBAC, memverifikasi CoV (LLM/Jev),
    dan menjalankan perkakas hanya jika disetujui.
    """
    verifier = cov_verifier or CoVVerifier()
    executor = tool_executor or MockToolExecutor()
    schemas = tool_schemas or {}

    # 1. Deteksi Otonom: Apakah agen peran memerlukan pemanggilan perkakas?
    has_tools, detected_tools = verifier.inspect_agent_response_for_tools(model_content)
    if not has_tools:
        # Jika tidak terdeteksi pemanggilan tools, CoV langsung passthrough
        # agar respon segera diteruskan ke user atau agen peran lain
        return {
            "has_tool_calls": False,
            "tool_calls": [],
            "tool_results": [],
            "repair_needed": False,
            "route_to": "USER_OR_PEER",
            "message": "Tidak ada pemanggilan perkakas. Respon langsung diserahkan ke pengguna/agen lain.",
        }

    tool_results: List[Dict[str, Any]] = []
    has_rejected_call = False
    latest_repair_feedback: Optional[str] = None

    for call in detected_tools:
        tool_id = call.get("tool_id", "")
        params = call.get("parameters", {})

        # 2. Verifikasi Izin RBAC Peran
        has_permission = await check_role_has_tool_permission(conn, allowed_tool_ids, tool_id)
        if not has_permission:
            err_msg = f"Akses ditolak: Peran [{role_id}] tidak memiliki izin memanggil perkakas [{tool_id}]."
            logger.warning(err_msg)
            tool_results.append({"tool_id": tool_id, "status": "error", "error": err_msg})
            continue

        risk_tier = 2 if any(k in tool_id for k in ("write", "execute", "create", "delete", "post")) else 1
        tool_schema = schemas.get(tool_id)

        # 3. Chain-of-Verification (CoV) Pre-Flight (Mode LLM atau Jev)
        cov_res: CoVInspectionResult = await verifier.verify_tool_invocation(
            conn=conn,
            project_id=project_id,
            ticket_id=ticket_id,
            role_id=role_id,
            tool_id=tool_id,
            parameters=params,
            schema=tool_schema,
            risk_tier=risk_tier,
            simulate_critic_pass=simulate_critic_pass,
        )

        if not cov_res.approved:
            has_rejected_call = True
            latest_repair_feedback = cov_res.repair_feedback
            logger.warning(
                f"[CoV Mode:{cov_res.mode}] Tool [{tool_id}] ditolak. Feedback perbaikan: {latest_repair_feedback}"
            )
            # Kembalikan penolakan ke agen peran agar agen peran melakukan self-repair
            tool_results.append({
                "tool_id": tool_id,
                "status": "rejected_by_cov",
                "mode": cov_res.mode,
                "tier": cov_res.tier_evaluated,
                "feedback": latest_repair_feedback,
                "missing_or_invalid": cov_res.missing_or_invalid_params,
            })
            continue

        # 4. Eksekusi Perkakas oleh Agen Peran (Setelah Disetujui CoV)
        exec_output = await executor.execute(tool_id, params)

        # 5. Batasi output maksimal 50KB (Invarian Suci 7)
        output_str = json.dumps(exec_output)
        if len(output_str) > 50000:
            output_str = output_str[:50000] + "... [DIPANGKAS_KARENA_MELEBIHI_50KB]"
            exec_output = {"status": "truncated", "data": output_str}

        tool_results.append({
            "tool_id": tool_id,
            "status": "success",
            "output": exec_output,
        })

        # Pancarkan event tool call ke stream Oasis
        await insert_message(
            conn,
            project_id=project_id,
            stream_category="EXECUTION_HANDOFFS",
            event_type="TOOL_CALL",
            content=f"Eksekusi disetujui CoV `{tool_id}`: {output_str[:300]}",
            sender_role_id=role_id,
            metadata={"ticket_id": ticket_id, "tool_id": tool_id, "cov_mode": cov_res.mode},
        )

    return {
        "has_tool_calls": True,
        "tool_calls": detected_tools,
        "tool_results": tool_results,
        "repair_needed": has_rejected_call,
        "repair_feedback": latest_repair_feedback,
        "route_to": "TOOL_EXECUTION_OR_REPAIR",
    }
