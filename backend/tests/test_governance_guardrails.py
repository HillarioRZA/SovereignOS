"""
Unit Tests for Governance Guardrails: Circuit Breaker, FinOps Guardrails, & Finance Repo.
Mematuhi Foreign Key Constraints dan Invarian Suci 10 (Anti-Loop Circuit Breaker).
"""

import os
import tempfile
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.db.repos.ticket_repo import get_ticket
from app.db.repos.finance_repo import (
    record_token_spend,
    record_venture_financial_entry,
    get_venture_pnl_summary,
    get_ticket_token_spend,
)
from app.engine.governance.circuit_breaker import AgentCircuitBreaker
from app.engine.governance.financial_guardrail import FinancialCircuitBreaker


@pytest.fixture
async def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    async with get_db_connection(path) as conn:
        await execute_ddl_migrations(conn)
        await conn.commit()
    yield path
    for ext in ["", "-wal", "-shm"]:
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


async def _seed_governance_parents(conn, project_id: str):
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_gov', 'Gov Div', 'gov', 'Governance')"
    )
    for r_id, handle in [("role_gov_fe", "@fe"), ("role_gov_be", "@be"), ("role_cfo", "@cfo")]:
        await conn.execute(
            """
            INSERT OR IGNORE INTO corporate_roles 
            (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
            VALUES (?, 'div_gov', ?, 'Role', 'Desc', 'Soul', 'SOP')
            """,
            (r_id, handle),
        )
    await conn.execute(
        "INSERT OR IGNORE INTO projects (id, name, founder_vision, product_archetype) VALUES (?, 'Gov Project', 'Vision', 'WEB_SAAS')",
        (project_id,),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_circuit_breaker_3_turn_freeze_and_ceo_override(temp_db):
    """Memastikan debat 3 turn tanpa kemajuan membekukan tiket ke BLOCKED_LOOP_DETECTED dan CEO bisa override."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "p_cb_test"
        t_id = "tkt_cb_01"
        await _seed_governance_parents(conn, proj_id)

        await conn.execute(
            """
            INSERT INTO corporate_tickets 
            (id, project_id, assigned_role_id, title, description, acceptance_criteria, status)
            VALUES (?, ?, 'role_gov_fe', 'Debate Task', 'Desc', 'AC', 'IN_PROGRESS')
            """,
            (t_id, proj_id),
        )
        await conn.commit()

        cb = AgentCircuitBreaker(max_turns=3)

        # Putaran 1 & 2: Masih di bawah batas
        blocked_1 = await cb.record_consultation_turn(conn, t_id, "@fe", "@be", "Schema debating turn 1")
        assert blocked_1 is False
        blocked_2 = await cb.record_consultation_turn(conn, t_id, "@be", "@fe", "Schema debating turn 2")
        assert blocked_2 is False

        # Putaran 3: Batas tercapai -> Terpicu pembekuan
        blocked_3 = await cb.record_consultation_turn(conn, t_id, "@fe", "@be", "Schema debating turn 3")
        assert blocked_3 is True

        tkt = await get_ticket(conn, t_id)
        assert tkt["status"] == "BLOCKED_LOOP_DETECTED"

        # CEO Override: FORCE_PROCEED -> status menjadi DONE
        override_res = await cb.execute_ceo_override(conn, t_id, "FORCE_PROCEED")
        assert override_res["status"] == "DONE"

        tkt_after = await get_ticket(conn, t_id)
        assert tkt_after["status"] == "DONE"


@pytest.mark.asyncio
async def test_finops_dual_ledger_and_budget_freeze(temp_db):
    """Memastikan pencatatan FinOps token ledger dan venture financial ledger berjalan terisolasi."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "p_fin_test"
        t_id = "tkt_fin_01"
        await _seed_governance_parents(conn, proj_id)

        await conn.execute(
            """
            INSERT INTO corporate_tickets 
            (id, project_id, assigned_role_id, title, description, acceptance_criteria, status)
            VALUES (?, ?, 'role_gov_fe', 'FinOps Task', 'Desc', 'AC', 'IN_PROGRESS')
            """,
            (t_id, proj_id),
        )
        await conn.commit()

        # 1. Catat penggunaan token AI
        await record_token_spend(
            conn=conn,
            project_id=proj_id,
            ticket_id=t_id,
            role_id="role_gov_fe",
            model_provider="anthropic",
            model_name="claude-3-7-sonnet",
            prompt_tokens=50000,
            cached_prompt_tokens=20000,
            completion_tokens=5000,
            cost_usd=0.25,
        )
        spend = await get_ticket_token_spend(conn, t_id)
        assert spend["total_tokens"] == 75000
        assert spend["total_cost_usd"] == 0.25

        # 2. Catat entri keuangan bisnis riil (P&L)
        await record_venture_financial_entry(
            conn=conn,
            project_id=proj_id,
            entry_type="REVENUE",
            amount_usd=1200.0,
            period_month="2026-10",
            notes="Enterprise B2B Subscription",
            recorded_by_role_id="role_cfo",
        )
        await record_venture_financial_entry(
            conn=conn,
            project_id=proj_id,
            entry_type="OPEX_INFRA",
            amount_usd=200.0,
            period_month="2026-10",
            notes="Cloud VPS & S3 Hosting",
            recorded_by_role_id="role_cfo",
        )

        pnl = await get_venture_pnl_summary(conn, proj_id, "2026-10")
        assert pnl["total_revenue"] == 1200.0
        assert pnl["total_opex"] == 200.0
        assert pnl["net_profit"] == 1000.0

        # 3. Uji pembekuan anggaran finansial tiket (FinancialCircuitBreaker)
        fin_guard = FinancialCircuitBreaker(max_tokens=100000, max_cost=1.0)
        is_frozen = await fin_guard.check_and_enforce_budget(
            conn=conn,
            ticket_id=t_id,
            tokens_spent=120000,
            cost_usd=1.50,
        )
        assert is_frozen is True

        tkt_frozen = await get_ticket(conn, t_id)
        assert tkt_frozen["status"] == "FROZEN_PENDING_APPROVAL"

        # 4. Topup persetujuan Founder
        topup_res = await fin_guard.approve_founder_budget_topup(conn, t_id, additional_tokens=100000)
        assert topup_res["status"] == "READY"
        tkt_unfrozen = await get_ticket(conn, t_id)
        assert tkt_unfrozen["status"] == "READY"
