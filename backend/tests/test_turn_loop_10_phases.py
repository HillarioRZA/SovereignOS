"""
Comprehensive Integration Test Suite untuk 10-Phase Turn Loop Engine & Dynamic Node.
Menguji eksekusi siklus penuh turn loop, integrasi mock router, Hold Ticket instant abort,
pencatatan token ledger, dan mention relay.
"""

import os
import tempfile
import pytest
import aiosqlite
import httpx

from app.db.schemas import execute_ddl_migrations
from app.db.repos.role_repo import upsert_role
from app.db.repos.ticket_repo import get_ticket, hold_ticket
from app.engine.roles.dynamic_node import DynamicNode
from app.engine.roles.mention_relay import dispatch_scoped_mention
from app.engine.turn.turn_facade import run_turn_cycle, TurnCycleResult
from app.engine.tools.mock_executor import MockToolExecutor
from app.gateway.model_router import SovereignModelRouter


@pytest.fixture
async def seeded_turn_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = OFF;")
        await execute_ddl_migrations(conn)

        # 1. Setup Proyek
        await conn.execute(
            "INSERT INTO projects (id, name, founder_vision, product_archetype) VALUES ('proj_mvp', 'Sovereign MVP', 'Build Autonomous SaaS', 'WEB_SAAS')"
        )
        # 2. Setup Divisi & Peran
        await conn.execute(
            "INSERT INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_core', 'Core Engineering', 'core', 'Backend & Frontend')"
        )
        await upsert_role(
            conn=conn,
            role_id="role_fe_dev",
            division_id="div_core",
            handle_mention="@fe",
            name="Frontend Specialist",
            job_description="Specialist in React & Next.js",
            persona_prompt="You are a senior frontend engineer focused on UI perfection.",
            system_prompt_template="Follow design guidelines and output tools accurately.",
            tool_permissions=["builtin:read_file", "builtin:write_file"],
            model_provider="openai_compatible",
            model_name="deepseek-chat",
        )
        # 3. Setup Tiket
        await conn.execute(
            """
            INSERT INTO corporate_tickets (
                id, project_id, assigned_role_id, title, description,
                acceptance_criteria, status, priority
            ) VALUES (
                'tkt_301', 'proj_mvp', 'role_fe_dev', 'Buat Landing Page Hero',
                'Implementasikan komponen HeroSection.tsx dengan Tailwind CSS.',
                'Hero section responsif', 'READY', 'HIGH'
            )
            """
        )
        # 4. Setup baseline tools
        await conn.execute(
            """
            INSERT INTO tool_permissions_registry (tool_id, namespace, display_name, description, parameters_json_schema, risk_tier, is_active)
            VALUES 
                ('builtin:read_file', 'builtin', 'Read File', 'Read file', '{"type":"object"}', 1, 1),
                ('builtin:write_file', 'builtin', 'Write File', 'Write file', '{"type":"object"}', 2, 1)
            """
        )
        await conn.commit()
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_full_10_phase_turn_cycle_with_tool_call(seeded_turn_db):
    """Menguji eksekusi sukses 10-phase turn loop lengkap dengan pemanggilan perkakas."""
    async with aiosqlite.connect(seeded_turn_db) as conn:
        conn.row_factory = aiosqlite.Row

        # Mock respons model yang menghasilkan pemanggilan builtin:write_file
        def mock_llm_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": 'Saya membuat HeroSection.tsx.\n```json\n{"tool": "builtin:write_file", "parameters": {"file_path": "HeroSection.tsx", "content": "export default function Hero() { return <h1>Hero</h1>; }"}}\n```',
                                "reasoning_content": "Merancang struktur komponen Hero.",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 250,
                        "prompt_tokens_details": {"cached_tokens": 100},
                        "completion_tokens": 80,
                    },
                },
            )

        mock_transport = httpx.MockTransport(mock_llm_handler)
        router = SovereignModelRouter(transport=mock_transport)
        mock_executor = MockToolExecutor()

        # Jalankan 10-phase turn cycle
        result: TurnCycleResult = await run_turn_cycle(
            conn=conn,
            project_id="proj_mvp",
            ticket_id="tkt_301",
            role_id="role_fe_dev",
            router=router,
            tool_executor=mock_executor,
            simulate_critic_pass=True,
        )

        assert result.success is True
        assert result.status == "IN_PROGRESS"
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["status"] == "success"
        assert result.cost_usd > 0.0

        # Verifikasi bahwa file benar-benar ditulis di virtual filesystem mock executor
        assert "HeroSection.tsx" in mock_executor.virtual_fs

        # Verifikasi pencatatan di corporate_token_ledger
        cur = await conn.execute("SELECT * FROM corporate_token_ledger WHERE ticket_id = 'tkt_301'")
        ledger_row = await cur.fetchone()
        assert ledger_row is not None
        assert ledger_row["role_id"] == "role_fe_dev"
        assert ledger_row["prompt_tokens"] == 250
        assert ledger_row["cached_prompt_tokens"] == 100
        assert len(ledger_row["system_prompt_digest"]) == 64

        # Verifikasi pembaruan status tiket kumulatif
        ticket = await get_ticket(conn, "tkt_301")
        assert ticket["spent_tokens"] == 330
        assert ticket["spent_cost_usd"] > 0.0
        assert ticket["consultation_turns"] == 1


@pytest.mark.asyncio
async def test_instant_1_click_hold_ticket_stops_preflight(seeded_turn_db):
    """Menegakkan Invarian Suci 1 & 9: Tiket berstatus ON_HOLD berhenti seketika dengan 0 token."""
    async with aiosqlite.connect(seeded_turn_db) as conn:
        conn.row_factory = aiosqlite.Row

        # Founder menekan tombol Hold Ticket
        await hold_ticket(conn, "tkt_301")

        # Mock transport yang sengaja melempar AssertionError jika dipanggil
        def failing_handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("LLM TIDAK BOLEH DIPANGGIL SAAT TIKET BERSTATUS ON_HOLD!")

        mock_transport = httpx.MockTransport(failing_handler)
        router = SovereignModelRouter(transport=mock_transport)

        # Jalankan turn cycle
        result = await run_turn_cycle(
            conn=conn,
            project_id="proj_mvp",
            ticket_id="tkt_301",
            role_id="role_fe_dev",
            router=router,
        )

        # Preflight harus langsung menolak eksekusi tanpa memanggil model sama sekali (0 Token terbuang)
        assert result.success is False
        assert result.status == "ON_HOLD"
        assert "ON_HOLD" in result.message


@pytest.mark.asyncio
async def test_dynamic_node_and_mention_relay_isolation(seeded_turn_db):
    """Menguji eksekusi via DynamicNode dan isolasi instruksi @mention."""
    async with aiosqlite.connect(seeded_turn_db) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Test dispatch @mention dari Founder
        dispatched = await dispatch_scoped_mention(
            conn=conn,
            project_id="proj_mvp",
            raw_content="@fe ubah padding tombol menjadi 16px",
            ticket_id="tkt_301",
        )
        assert len(dispatched) == 1
        assert dispatched[0]["handle"] == "@fe"
        assert dispatched[0]["role_id"] == "role_fe_dev"

        # 2. Test DynamicNode instantiation
        node = await DynamicNode.from_handle(conn, "@fe")
        assert node is not None
        assert node.handle_mention == "@fe"
        assert node.name == "Frontend Specialist"
