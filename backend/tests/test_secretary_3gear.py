"""
Unit Tests for @secretary 3-Gear Command Dispatcher & @tool_builder Delegation.
Mematuhi Foreign Key Constraints dan Spesifikasi Secretary-Role.md.
"""

import json
import os
import tempfile
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.engine.roles.secretary_dispatcher import secretary_dispatcher


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


async def _seed_secretary_environment(conn):
    """Seed corporate_roles dan corporate_divisions untuk sekretaris dan pakar."""
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_executive', 'Executive', 'exec', 'Management')"
    )
    roles = [
        ("role_secretary", "@secretary", "Executive Personal Secretary"),
        ("role_cto", "@cto", "Chief Technology Officer"),
        ("role_tool_builder", "@tool_builder", "On-Demand Tool Maker"),
        ("role_fe", "@fe", "Frontend Developer"),
        ("role_qa", "@qa", "QA Engineer"),
    ]
    for r_id, handle, name in roles:
        await conn.execute(
            """
            INSERT OR IGNORE INTO corporate_roles 
            (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
            VALUES (?, 'div_executive', ?, ?, 'Desc', 'Soul', 'SOP')
            """,
            (r_id, handle, name),
        )
    await conn.commit()


@pytest.mark.asyncio
async def test_secretary_3_gear_dispatcher_routing(temp_db):
    """Menguji transmisi 3 gigi: Gigi 1 Personal, Gigi 2 Konsultasi Pakar, Gigi 3 Swarm Project."""
    async with get_db_connection(temp_db) as conn:
        await _seed_secretary_environment(conn)

        # 1. Gigi 1: Pertanyaan santai / memo personal
        res_g1 = await secretary_dispatcher.dispatch_command(
            conn=conn,
            user_prompt="Ingatkan saya besok jam 9 pagi ada meeting investor",
            founder_id="founder_reza",
        )
        assert res_g1["gear_selected"] == 1
        assert res_g1["personal_memory_isolated"] is True

        # Verifikasi tersimpan di corporate_wisdom dengan project_id = 'personal'
        cur = await conn.execute("SELECT * FROM corporate_wisdom WHERE project_id = 'personal'")
        row = await cur.fetchone()
        assert row is not None
        assert "meeting investor" in row["content"]

        # 2. Gigi 2: Konsultasi pakar ad-hoc ke @cto
        res_g2 = await secretary_dispatcher.dispatch_command(
            conn=conn,
            user_prompt="Tolong tanyakan ke @cto apakah arsitektur event bus kita siap production",
            founder_id="founder_reza",
        )
        assert res_g2["gear_selected"] == 2
        assert res_g2["consulted_role"] == "@cto"
        assert res_g2["scoped_dispatched"] is True

        # 3. Gigi 3: Instruksi pembuatan proyek baru
        res_g3 = await secretary_dispatcher.dispatch_command(
            conn=conn,
            user_prompt="Bikin proyek baru Landing Page SaaS AI Lawyer dengan archetype WEB_SAAS",
            founder_id="founder_reza",
        )
        assert res_g3["gear_selected"] == 3
        assert "project_id" in res_g3
        assert res_g3["tickets_created"] > 0


@pytest.mark.asyncio
async def test_secretary_delegate_to_tool_builder(temp_db):
    """Menguji pendelegasian kebutuhan tool baru ke @tool_builder."""
    async with get_db_connection(temp_db) as conn:
        await _seed_secretary_environment(conn)

        tool_spec = {
            "tool_id": "custom:scrape_sec_filings",
            "namespace": "custom",
            "display_name": "SEC Filings Scraper",
            "description": "Scrapes 10-K financial reports",
            "requires_human_approval": 1,
        }
        delegated = await secretary_dispatcher.delegate_to_tool_builder(conn, tool_spec)
        assert delegated["status"] == "QUEUED_FOR_BUILDER"
        assert delegated["escalated_to_ceo_gate"] is True
