"""
Unit Test Suite untuk CoV Gatekeeper (Mode LLM & Mode Jev) & Smart Guardian.
Menguji verifikasi Mode Jev, Mode LLM Critic, deteksi otonom tools,
pencegahan path traversal, dan pemindaian keamanan statis.
"""

import os
import tempfile
import pytest
import aiosqlite

from app.db.schemas import execute_ddl_migrations
from app.engine.governance.cov_verifier import CoVVerifier
from app.engine.governance.smart_guardian import scan_payload_safety, check_denial_circuit_breaker


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
async def test_cov_jev_mode_verification(temp_db):
    """Menguji verifikasi CoV dengan Mode Jev (TypeSafe AI System One)."""
    async with aiosqlite.connect(temp_db) as conn:
        conn.row_factory = aiosqlite.Row
        verifier = CoVVerifier(mode="jev")

        # 1. Parameter valid untuk builtin:read_file
        res = await verifier.verify_tool_invocation(
            conn=conn,
            project_id="proj_test",
            ticket_id="tkt_1",
            role_id="role_fe",
            tool_id="builtin:read_file",
            parameters={"file_path": "frontend/App.tsx"},
            schema={"required": ["file_path"]},
        )
        assert res.approved is True
        assert res.mode == "jev"
        assert res.tier_evaluated == 1
        assert res.verdict == "APPROVED"
        assert res.latency_ms >= 0.0

        # Verifikasi pencatatan di sentinel_audit_logs
        cur = await conn.execute("SELECT * FROM sentinel_audit_logs WHERE tool_id = 'builtin:read_file'")
        log = await cur.fetchone()
        assert log is not None
        assert log["tier_evaluated"] == 1
        assert log["verdict"] == "APPROVED"

        # 2. Parameter tidak lengkap (kekurangan file_path) -> Wajib REPAIR_REQUIRED
        res_invalid = await verifier.verify_tool_invocation(
            conn=conn,
            project_id="proj_test",
            ticket_id="tkt_1",
            role_id="role_fe",
            tool_id="builtin:read_file",
            parameters={},
            schema={"required": ["file_path"]},
        )
        assert res_invalid.approved is False
        assert res_invalid.verdict == "REPAIR_REQUIRED"
        assert "file_path" in res_invalid.missing_or_invalid_params


@pytest.mark.asyncio
async def test_cov_llm_mode_with_critic_pass(temp_db):
    """Menguji verifikasi CoV dengan Mode LLM Critic (simulate_critic_pass)."""
    async with aiosqlite.connect(temp_db) as conn:
        conn.row_factory = aiosqlite.Row
        verifier = CoVVerifier(mode="llm")

        res = await verifier.verify_tool_invocation(
            conn=conn,
            project_id="proj_test",
            ticket_id="tkt_2",
            role_id="role_be",
            tool_id="builtin:write_file",
            parameters={"file_path": "api/routes.py", "content": "from fastapi import APIRouter"},
            simulate_critic_pass=True,
        )
        assert res.approved is True
        assert res.mode == "llm"
        assert res.tier_evaluated == 2
        assert res.verdict == "APPROVED"


@pytest.mark.asyncio
async def test_cov_path_traversal_blocking(temp_db):
    """Menguji bahwa CoV memblokir path traversal '..' sebelum dieksekusi."""
    async with aiosqlite.connect(temp_db) as conn:
        conn.row_factory = aiosqlite.Row
        verifier = CoVVerifier(mode="jev")

        res = await verifier.verify_tool_invocation(
            conn=conn,
            project_id="proj_test",
            ticket_id="tkt_1",
            role_id="role_fe",
            tool_id="builtin:read_file",
            parameters={"file_path": "../../etc/passwd"},
        )
        assert res.approved is False
        assert res.verdict == "REJECTED"
        assert "traversal" in res.repair_feedback.lower()


def test_cov_autonomous_tool_detection():
    """Menguji pemisahan otonomi respon agen peran (perlu tools vs passthrough)."""
    verifier = CoVVerifier()

    # Kasus 1: Agen peran TIDAK butuh tools -> passthrough langsung ke user/agen lain
    text_no_tools = "Halo! Fitur autentikasi telah siap digunakan. Silakan cek dokumentasi."
    has_tools, tools = verifier.inspect_agent_response_for_tools(text_no_tools)
    assert has_tools is False
    assert len(tools) == 0

    # Kasus 2: Agen butuh pemanggilan tools -> serahkan ke CoV
    text_with_tools = 'Saya akan membaca file konfigurasi.\n```json\n{"tool": "builtin:read_file", "parameters": {"file_path": "config.json"}}\n```'
    has_tools_2, tools_2 = verifier.inspect_agent_response_for_tools(text_with_tools)
    assert has_tools_2 is True
    assert len(tools_2) == 1
    assert tools_2[0]["tool_id"] == "builtin:read_file"


def test_smart_guardian_static_scanning():
    """Menguji pemindaian keamanan statis Smart Guardian."""
    safe_rm, err_rm = scan_payload_safety("rm -rf /")
    assert safe_rm is False
    assert "penghapusan" in err_rm.lower()

    safe_shadow, err_shadow = scan_payload_safety("cat /etc/shadow")
    assert safe_shadow is False
    assert "kredensial" in err_shadow.lower()

    safe_code, err_code = scan_payload_safety("const [count, setCount] = useState(0);")
    assert safe_code is True
    assert err_code is None

    assert check_denial_circuit_breaker(consecutive_failures=2, max_threshold=3) is False
    assert check_denial_circuit_breaker(consecutive_failures=3, max_threshold=3) is True
