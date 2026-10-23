"""
Repository Keuangan Korporat & FinOps AI (corporate_token_ledger & venture_financial_ledger).
Menyediakan pelacakan ganda:
1. Konsumsi token model LLM (prompt, cached, completion, cost_usd).
2. Buku besar keuangan bisnis riil (Revenue, COGS, OPEX, Net Profit P&L).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import aiosqlite

from app.core.logger import logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def record_token_spend(
    conn: aiosqlite.Connection,
    project_id: str,
    ticket_id: Optional[str],
    role_id: str,
    model_provider: str,
    model_name: str,
    prompt_tokens: int,
    cached_prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    system_prompt_digest: str = "",
    tool_schema_digest: str = "",
) -> Dict[str, Any]:
    """Mencatat penggunaan token satu inferensi model ke corporate_token_ledger."""
    entry_id = f"tok_{uuid.uuid4().hex[:10]}"
    now_str = _now_iso()
    query = """
    INSERT INTO corporate_token_ledger (
        id, project_id, ticket_id, role_id, model_provider, model_name,
        system_prompt_digest, tool_schema_digest, prompt_tokens,
        cached_prompt_tokens, completion_tokens, cost_usd, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    RETURNING *;
    """
    cur = await conn.execute(
        query,
        (
            entry_id,
            project_id,
            ticket_id,
            role_id,
            model_provider,
            model_name,
            system_prompt_digest,
            tool_schema_digest,
            prompt_tokens,
            cached_prompt_tokens,
            completion_tokens,
            cost_usd,
            now_str,
        ),
    )
    row = await cur.fetchone()
    await conn.commit()
    return dict(row) if row else {}


async def get_ticket_token_spend(
    conn: aiosqlite.Connection, ticket_id: str
) -> Dict[str, Any]:
    """Mengagregasi total token dan biaya finansial yang dihabiskan untuk tiket tertentu."""
    query = """
    SELECT 
        COALESCE(SUM(prompt_tokens + cached_prompt_tokens + completion_tokens), 0) as total_tokens,
        COALESCE(SUM(cost_usd), 0.0) as total_cost_usd,
        COUNT(*) as total_calls
    FROM corporate_token_ledger
    WHERE ticket_id = ?
    """
    cur = await conn.execute(query, (ticket_id,))
    row = await cur.fetchone()
    return {
        "ticket_id": ticket_id,
        "total_tokens": int(row["total_tokens"]) if row else 0,
        "total_cost_usd": round(float(row["total_cost_usd"]), 4) if row else 0.0,
        "total_calls": int(row["total_calls"]) if row else 0,
    }


async def record_venture_financial_entry(
    conn: aiosqlite.Connection,
    project_id: str,
    entry_type: str,
    amount_usd: float,
    period_month: str,
    notes: Optional[str],
    recorded_by_role_id: str,
    is_recurring: int = 0,
) -> Dict[str, Any]:
    """Mencatat entri keuangan bisnis riil (P&L) ke venture_financial_ledger."""
    entry_id = f"fin_{uuid.uuid4().hex[:10]}"
    now_str = _now_iso()
    query = """
    INSERT INTO venture_financial_ledger (
        id, project_id, entry_type, amount_usd, is_recurring,
        period_month, notes, recorded_by_role_id, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    RETURNING *;
    """
    cur = await conn.execute(
        query,
        (
            entry_id,
            project_id,
            entry_type,
            amount_usd,
            is_recurring,
            period_month,
            notes,
            recorded_by_role_id,
            now_str,
        ),
    )
    row = await cur.fetchone()
    await conn.commit()
    return dict(row) if row else {}


async def get_venture_pnl_summary(
    conn: aiosqlite.Connection, project_id: str, period_month: Optional[str] = None
) -> Dict[str, Any]:
    """Menghitung ringkasan laba/rugi (P&L) proyek bisnis venture."""
    if period_month:
        cur = await conn.execute(
            "SELECT entry_type, SUM(amount_usd) as total FROM venture_financial_ledger WHERE project_id = ? AND period_month = ? GROUP BY entry_type",
            (project_id, period_month),
        )
    else:
        cur = await conn.execute(
            "SELECT entry_type, SUM(amount_usd) as total FROM venture_financial_ledger WHERE project_id = ? GROUP BY entry_type",
            (project_id,),
        )
    rows = await cur.fetchall()

    revenue = 0.0
    cogs = 0.0
    opex = 0.0
    token_cost = 0.0

    for r in rows:
        t = r["entry_type"]
        val = float(r["total"])
        if t == "REVENUE":
            revenue += val
        elif t == "COGS":
            cogs += val
        elif t.startswith("OPEX"):
            opex += val
        elif t == "AI_TOKEN_COST":
            token_cost += val

    net_profit = revenue - (cogs + opex + token_cost)
    return {
        "project_id": project_id,
        "period_month": period_month,
        "total_revenue": round(revenue, 2),
        "total_cogs": round(cogs, 2),
        "total_opex": round(opex, 2),
        "total_token_cost": round(token_cost, 2),
        "net_profit": round(net_profit, 2),
    }
