"""
Unit Tests for PR Quorum Engine and Deterministic Blackbox Flight Recorder.
Mematuhi Foreign Key Constraints dan Invarian Suci 7 & 10.
"""

import os
import tempfile
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.db.repos.pr_repo import pr_repo
from app.engine.governance.pr_quorum_engine import pr_quorum_engine
from app.engine.governance.flight_recorder import flight_recorder


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


async def _seed_pr_parents(conn, project_id: str, ticket_id: str):
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_pr', 'PR Div', 'pr', 'Quality')"
    )
    for r_id, handle in [("role_author", "@author"), ("role_qa_rev", "@qa_rev"), ("role_sec_rev", "@sec_rev")]:
        await conn.execute(
            """
            INSERT OR IGNORE INTO corporate_roles 
            (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
            VALUES (?, 'div_pr', ?, 'Role', 'Desc', 'Soul', 'SOP')
            """,
            (r_id, handle),
        )
    await conn.execute(
        "INSERT OR IGNORE INTO projects (id, name, founder_vision, product_archetype) VALUES (?, 'PR Project', 'Vision', 'WEB_SAAS')",
        (project_id,),
    )
    await conn.execute(
        """
        INSERT OR IGNORE INTO corporate_tickets 
        (id, project_id, assigned_role_id, title, description, acceptance_criteria, status)
        VALUES (?, ?, 'role_author', 'Ticket for PR', 'Desc', 'AC', 'IN_PROGRESS')
        """,
        (ticket_id, project_id),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_pr_quorum_engine_requires_2_independent_approvals(temp_db):
    """Memastikan PR hanya disetujui jika mendapatkan minimal >= 2 approval independen tanpa penolakan."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "p_pr_test"
        t_id = "tkt_pr_01"
        pr_id = "pr_101"
        await _seed_pr_parents(conn, proj_id, t_id)

        # 1. Buat Pull Request
        pr = await pr_repo.create_pr(
            conn=conn,
            pr_id=pr_id,
            project_id=proj_id,
            ticket_id=t_id,
            author_role_id="role_author",
            diff_content="+ const api_token = loadSecret();",
        )
        assert pr["status"] == "OPEN"

        # 2. Review pertama dari QA: APPROVED (1/2 approval -> belum kuorum)
        rev1 = await pr_quorum_engine.submit_review(
            conn=conn,
            pr_id=pr_id,
            reviewer_role_id="role_qa_rev",
            verdict="APPROVED",
            security_score=100,
            comments=["Unit test pass 100%."],
        )
        assert rev1["quorum_met"] is False
        assert rev1["status"] == "OPEN"

        pr_mid = await pr_repo.get_pr(conn, pr_id)
        assert pr_mid["status"] == "OPEN"

        # 3. Review kedua dari Security: APPROVED (2/2 approval -> KUORUM TERCAPAI)
        rev2 = await pr_quorum_engine.submit_review(
            conn=conn,
            pr_id=pr_id,
            reviewer_role_id="role_sec_rev",
            verdict="APPROVED",
            security_score=95,
            comments=["No OWASP AST vulnerabilities found."],
        )
        assert rev2["quorum_met"] is True
        assert rev2["status"] == "APPROVED"

        pr_final = await pr_repo.get_pr(conn, pr_id)
        assert pr_final["status"] == "APPROVED"


def test_flight_recorder_append_and_replay(tmp_path):
    """Memastikan perekam blackbox flight recorder menyimpan log stream dan mampu melakukan time-travel replay."""
    fr = flight_recorder
    fr.set_log_dir(tmp_path)

    proj_id = "proj_flight_test"
    ev1 = fr.record_step(proj_id, "role_author", "FILE_EDIT", {"file": "auth.py", "lines": 45})
    assert ev1["step_index"] == 1

    ev2 = fr.record_step(proj_id, "role_qa_rev", "TEST_EXEC", {"passed": True, "coverage": 92.5})
    assert ev2["step_index"] == 2

    # Time-travel replay
    replayed_1 = fr.replay_step(proj_id, 1)
    assert replayed_1 is not None
    assert replayed_1["payload"]["file"] == "auth.py"

    replayed_2 = fr.replay_step(proj_id, 2)
    assert replayed_2 is not None
    assert replayed_2["payload"]["passed"] is True
