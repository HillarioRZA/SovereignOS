"""
Unit Tests for Office Engine: office_relay, office_dispatch, & war_room_moderator.
Mematuhi Foreign Key Constraints (PRAGMA foreign_keys = ON) dan Invarian Suci 1 & 9.
"""

import os
import tempfile
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.db.repos.ticket_repo import get_ticket
from app.engine.turn.turn_preflight import execute_turn_preflight, is_ticket_interrupted
from app.engine.orchestrator.file_lock_manager import file_lock_manager
from app.engine.office.office_relay import office_relay
from app.engine.office.office_dispatch import office_dispatch
from app.engine.office.war_room_moderator import war_room_moderator


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


async def _seed_parent_entities(conn, project_id: str, division_id: str, role_id: str, handle: str):
    """Helper untuk menyemai entitas induk agar mematuhi constraint foreign key."""
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES (?, ?, ?, ?)",
        (division_id, "Engineering", "engineering", "Core Dev"),
    )
    await conn.execute(
        """
        INSERT OR IGNORE INTO corporate_roles 
        (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (role_id, division_id, handle, "Frontend Specialist", "UI Dev", "Soul", "SOP"),
    )
    await conn.execute(
        """
        INSERT OR IGNORE INTO projects 
        (id, name, founder_vision, product_archetype)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, "Test Project", "Vision 1", "WEB_SAAS"),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_1_click_hold_ticket_preemption_and_lock_release(temp_db):
    """Memastikan hold_ticket_action() mengubah status, memicu interrupt ke preflight, dan melepas lock."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "proj_office_test"
        div_id = "div_office_fe"
        role_id = "role_office_fe"
        tkt_id = "tkt_office_hold_01"

        await _seed_parent_entities(conn, proj_id, div_id, role_id, "@fe")

        # Insert tiket dalam status IN_PROGRESS
        await conn.execute(
            """
            INSERT INTO corporate_tickets 
            (id, project_id, assigned_role_id, title, description, acceptance_criteria, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tkt_id, proj_id, role_id, "Build Header", "Build UI Header", "AC", "IN_PROGRESS"),
        )
        await conn.commit()

        # Agen memegang lock berkas
        await file_lock_manager.acquire(proj_id, "src/Header.tsx")

        # 1-Click Hold Ticket dipicu Founder
        hold_res = await office_dispatch.hold_ticket_action(conn, proj_id, tkt_id)
        assert hold_res["status"] == "ON_HOLD"

        # 1. Status di DB harus ON_HOLD
        tkt = await get_ticket(conn, tkt_id)
        assert tkt["status"] == "ON_HOLD"

        # 2. Sinyal interupsi ke turn_preflight aktif
        assert is_ticket_interrupted(tkt_id) is True
        preflight = await execute_turn_preflight(conn, tkt_id)
        assert preflight.can_proceed is False
        assert preflight.status == "ON_HOLD"

        # 3. Kunci berkas telah dilepas otomatis (dapat di-lock kembali tanpa hang)
        acquired = False
        async with file_lock_manager.lock(proj_id, "src/Header.tsx"):
            acquired = True
        assert acquired is True

        # Resume ticket action
        resume_res = await office_dispatch.resume_ticket_action(conn, tkt_id)
        assert resume_res["status"] == "READY"
        assert is_ticket_interrupted(tkt_id) is False


@pytest.mark.asyncio
async def test_screenshare_telemetry_emission(temp_db):
    """Memastikan office_relay memancarkan telemetri screen-share dan menyimpan data ke DB."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "proj_telemetry_test"
        div_id = "div_tel"
        role_id = "role_tel_fe"
        tkt_id = "tkt_tel_02"

        await _seed_parent_entities(conn, proj_id, div_id, role_id, "@fe")
        await conn.execute(
            """
            INSERT INTO corporate_tickets 
            (id, project_id, assigned_role_id, title, description, acceptance_criteria, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tkt_id, proj_id, role_id, "Telemetry Task", "Desc", "AC", "IN_PROGRESS"),
        )
        await conn.commit()

        telemetry = await office_relay.emit_screenshare_telemetry(
            conn=conn,
            project_id=proj_id,
            ticket_id=tkt_id,
            role_handle="@fe",
            status_bubble="Coding HeaderCard.tsx...",
            active_file_path="src/HeaderCard.tsx",
            live_scratchpad="1. Setup hooks\n2. Render JSX",
            live_diff_preview="+ const x = 1;",
        )
        assert telemetry["ticket_id"] == tkt_id
        assert telemetry["status_bubble"] == "Coding HeaderCard.tsx..."

        # Verifikasi terupdate di database
        tkt = await get_ticket(conn, tkt_id)
        assert tkt["active_file_path"] == "src/HeaderCard.tsx"
        assert tkt["status_bubble_text"] == "Coding HeaderCard.tsx..."


@pytest.mark.asyncio
async def test_war_room_moderation_deterministic_flow(temp_db):
    """Memastikan All-Hands War Room berjalan deterministik dengan moderasi CoS & CTO."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "proj_warroom_test"
        await conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, founder_vision, product_archetype) VALUES (?, ?, ?, ?)",
            (proj_id, "War Room Project", "Vision", "WEB_SAAS"),
        )
        await conn.commit()

        turns = await war_room_moderator.start_war_room_session(
            conn=conn,
            project_id=proj_id,
            founder_problem="Payment gateway returns HTTP 500 intermittently",
            participants=["@cos", "@cto", "@cfo", "@pm"],
        )
        assert len(turns) == 4
        assert turns[0]["speaker"] == "Founder"
        assert turns[1]["speaker"] == "@cto"
        assert turns[2]["speaker"] == "@cfo_pm"
        assert turns[3]["speaker"] == "@cos"
        assert "Payment gateway" in turns[0]["statement"]
