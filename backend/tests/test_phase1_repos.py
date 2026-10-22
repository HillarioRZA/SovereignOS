"""
Unit test suite untuk repositori database Fase 1 dan MockToolExecutor.
Menguji ticket_repo (claim atomik & hold ticket), tool_repo, message_repo, dan mock_executor.
"""

import os
import tempfile
import pytest
import aiosqlite

from app.db.schemas import execute_ddl_migrations
from app.db.repos.ticket_repo import (
    claim_ready_ticket,
    get_ticket,
    hold_ticket,
    update_screenshare_telemetry,
)
from app.db.repos.tool_repo import (
    register_tool_permission,
    get_tool_permission,
    get_sorted_tools_for_role,
)
from app.db.repos.message_repo import (
    insert_message,
    list_stream_messages,
    list_scoped_messages_for_turn,
)
from app.engine.tools.mock_executor import MockToolExecutor


@pytest.fixture
async def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = OFF;")
        await execute_ddl_migrations(conn)
        await conn.commit()
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_ticket_repo_atomic_claim_and_hold(temp_db):
    """Menguji operasi klaim tiket atomik dan 1-klik hold ticket."""
    async with aiosqlite.connect(temp_db) as conn:
        conn.row_factory = aiosqlite.Row

        # Setup proyek dan tiket
        await conn.execute("INSERT INTO projects (id, name, founder_vision, product_archetype) VALUES ('proj_1', 'Test', 'Vision', 'WEB_SAAS')")
        await conn.execute("INSERT INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_eng', 'Engineering', 'eng', 'Purpose')")
        await conn.execute("INSERT INTO corporate_roles (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template) VALUES ('role_be', 'div_eng', '@be', 'Backend', 'Desc', 'Soul', 'SOP')")
        
        await conn.execute("""
            INSERT INTO corporate_tickets (id, project_id, assigned_role_id, title, description, acceptance_criteria, status, priority)
            VALUES ('tkt_101', 'proj_1', 'role_be', 'API Auth', 'Desc', 'Criteria', 'READY', 'HIGH')
        """)
        await conn.commit()

        # 1. Atomic claim tiket
        claimed = await claim_ready_ticket(conn, project_id="proj_1", worker_role_id="role_be", lease_duration_seconds=30)
        assert claimed is not None
        assert claimed["id"] == "tkt_101"
        assert claimed["status"] == "IN_PROGRESS"
        assert claimed["lease_owner"] == "role_be"

        # Klaim kedua harus None karena tiket sudah diklaim
        second_claim = await claim_ready_ticket(conn, project_id="proj_1", worker_role_id="role_be")
        assert second_claim is None

        # 2. Update screen share telemetry
        await update_screenshare_telemetry(
            conn,
            ticket_id="tkt_101",
            active_file_path="backend/api.py",
            live_scratchpad_text="Menyusun JWT token handler...",
            status_bubble_text="Coding Auth API",
        )
        updated = await get_ticket(conn, "tkt_101")
        assert updated["active_file_path"] == "backend/api.py"
        assert "JWT" in updated["live_scratchpad_text"]

        # 3. 1-Klik Hold Ticket
        success = await hold_ticket(conn, ticket_id="tkt_101")
        assert success is True
        held = await get_ticket(conn, "tkt_101")
        assert held["status"] == "ON_HOLD"
        assert held["lease_owner"] is None


@pytest.mark.asyncio
async def test_tool_repo_registry(temp_db):
    """Menguji pendaftaran dan kueri izin perkakas di tool_permissions_registry."""
    async with aiosqlite.connect(temp_db) as conn:
        conn.row_factory = aiosqlite.Row

        await register_tool_permission(
            conn,
            tool_id="custom:deploy_cloud",
            namespace="custom",
            display_name="Deploy to Cloud",
            description="Deploy ke server produksi",
            parameters_json_schema={"type": "object", "properties": {"env": {"type": "string"}}},
            risk_tier=2,
            requires_human_approval=1,
        )

        tool = await get_tool_permission(conn, "custom:deploy_cloud")
        assert tool is not None
        assert tool["risk_tier"] == 2
        assert tool["requires_human_approval"] == 1

        sorted_tools, digest = await get_sorted_tools_for_role(conn, ["custom:deploy_cloud"])
        assert len(sorted_tools) == 1
        assert sorted_tools[0]["name"] == "custom:deploy_cloud"
        assert len(digest) == 64  # SHA-256 length


@pytest.mark.asyncio
async def test_message_repo_streams_and_scoped_mention(temp_db):
    """Menguji filter 4-kategori stream dan isolasi instruksi @mention."""
    async with aiosqlite.connect(temp_db) as conn:
        conn.row_factory = aiosqlite.Row

        # Kirim pesan stream EXECUTION_HANDOFFS umum
        m1 = await insert_message(
            conn,
            project_id="proj_1",
            stream_category="EXECUTION_HANDOFFS",
            event_type="HANDOFF",
            content="Tiket selesai diserahkan ke QA",
            sender_role_id="role_be",
        )
        assert m1 is not None

        # Kirim pesan terarah @mention scoped ke role_fe
        m2 = await insert_message(
            conn,
            project_id="proj_1",
            stream_category="GENERAL_THOUGHT",
            event_type="THOUGHT",
            content="@fe sesuaikan warna tombol ke Obsidian Blue",
            sender_role_id="founder",
            scoped_recipient_role_id="role_fe",
        )
        assert m2 is not None

        # Kueri stream EXECUTION_HANDOFFS
        handoffs = await list_stream_messages(conn, project_id="proj_1", stream_category="EXECUTION_HANDOFFS")
        assert len(handoffs) == 1
        assert handoffs[0]["event_type"] == "HANDOFF"

        # Kueri scoped messages untuk role_fe (harus menerima m1 umum dan m2 miliknya)
        fe_msgs = await list_scoped_messages_for_turn(conn, project_id="proj_1", current_role_id="role_fe")
        assert len(fe_msgs) == 2

        # Kueri scoped messages untuk role_qa (hanya menerima m1 umum, TIDAK boleh melihat m2 milik role_fe)
        qa_msgs = await list_scoped_messages_for_turn(conn, project_id="proj_1", current_role_id="role_qa")
        assert len(qa_msgs) == 1
        assert qa_msgs[0]["id"] == m1


@pytest.mark.asyncio
async def test_mock_tool_executor():
    """Menguji eksekutor perkakas mock in-memory."""
    executor = MockToolExecutor()

    # Test list directory
    res_list = await executor.execute("builtin:list_directory", {})
    assert res_list["status"] == "success"
    assert "README.md" in res_list["files"]

    # Test read file
    res_read = await executor.execute("builtin:read_file", {"file_path": "README.md"})
    assert res_read["status"] == "success"
    assert "Project Sovereign" in res_read["content"]

    # Test write file
    res_write = await executor.execute("builtin:write_file", {"file_path": "test.txt", "content": "Hello World"})
    assert res_write["status"] == "success"

    # Test read new file
    res_read_new = await executor.execute("builtin:read_file", {"file_path": "test.txt"})
    assert res_read_new["content"] == "Hello World"

    # Test execute code
    res_code = await executor.execute("ptc:execute_code", {"code": "print('test')"})
    assert res_code["status"] == "success"
    assert "Mock PTC Output" in res_code["stdout"]
