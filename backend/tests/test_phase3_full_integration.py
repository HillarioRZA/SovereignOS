"""
End-to-End Integration Test for Phase 3 Parallel Orchestrator & Governance Engine.
Memverifikasi integrasi mulus:
@secretary (Gigi 3) -> Runbook DAG -> Swarm Claim -> 1-Click Hold/Resume ->
Dependency Progression -> PR Submission -> Peer Quorum Gate -> Flight Recorder.
"""

import json
import os
import tempfile
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.db.repos.ticket_repo import get_ticket, complete_ticket
from app.db.repos.pr_repo import pr_repo
from app.engine.roles.secretary_dispatcher import secretary_dispatcher
from app.engine.orchestrator.kanban_swarm import AutonomousKanbanSwarm
from app.engine.office.office_dispatch import office_dispatch
from app.engine.turn.turn_preflight import execute_turn_preflight, is_ticket_interrupted
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


async def _seed_full_phase3_environment(conn):
    """Seed corporate_divisions and corporate_roles untuk seluruh aktor Phase 3."""
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_exec', 'Executive', 'exec', 'Management')"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_dev', 'Engineering', 'dev', 'Development')"
    )
    roles = [
        ("role_sec", "div_exec", "@secretary", "Secretary"),
        ("role_pm", "div_exec", "@pm", "Product Manager"),
        ("role_fe", "div_dev", "@fe", "Frontend Dev"),
        ("role_qa", "div_dev", "@qa", "QA Engineer"),
        ("role_sec_eng", "div_dev", "@security", "Security Auditor"),
    ]
    for r_id, d_id, handle, name in roles:
        await conn.execute(
            """
            INSERT OR IGNORE INTO corporate_roles 
            (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
            VALUES (?, ?, ?, ?, 'Desc', 'Soul', 'SOP')
            """,
            (r_id, d_id, handle, name),
        )
    await conn.commit()


@pytest.mark.asyncio
async def test_phase3_complete_e2e_orchestration_cycle(temp_db, tmp_path):
    """Verifikasi end-to-end seluruh siklus orkestrasi Fase 3."""
    flight_recorder.set_log_dir(tmp_path)

    async with get_db_connection(temp_db) as conn:
        await _seed_full_phase3_environment(conn)

        # 1. Founder memerintahkan pembuatan proyek baru ke @secretary via Gigi 3
        sec_result = await secretary_dispatcher.dispatch_command(
            conn=conn,
            user_prompt="Bikin proyek SaaS AI Video Editor baru dengan archetype WEB_SAAS",
            founder_id="founder_reza",
        )
        assert sec_result["gear_selected"] == 3
        project_id = sec_result["project_id"]
        assert sec_result["tickets_created"] == 3
        flight_recorder.record_step(project_id, "role_sec", "PROJECT_DEPLOYED", sec_result)

        # 2. Kanban swarm runner memindai dan mengklaim tiket pertama (Discovery / @pm)
        swarm = AutonomousKanbanSwarm(max_concurrency=3)
        claimed_tickets = await swarm.scan_and_claim_tickets(conn, project_id)
        assert len(claimed_tickets) == 1
        first_ticket = claimed_tickets[0]
        assert first_ticket["status"] == "IN_PROGRESS"
        t_id = first_ticket["id"]

        # 3. Founder memicu 1-Klik Hold Ticket dari Screen-Share Pane
        hold_res = await office_dispatch.hold_ticket_action(conn, project_id, t_id)
        assert hold_res["status"] == "ON_HOLD"
        assert is_ticket_interrupted(t_id) is True

        preflight = await execute_turn_preflight(conn, t_id)
        assert preflight.can_proceed is False
        assert preflight.status == "ON_HOLD"
        flight_recorder.record_step(project_id, "founder", "HOLD_TICKET_TRIGGERED", {"ticket_id": t_id})

        # 4. Founder melanjutkan tiket kembali (Resume)
        resume_res = await office_dispatch.resume_ticket_action(conn, t_id)
        assert resume_res["status"] == "READY"
        assert is_ticket_interrupted(t_id) is False

        # 5. Selesaikan tiket pertama -> DONE
        await complete_ticket(conn, t_id, artifact_refs=["artifact_prd_spec"])
        tkt_done = await get_ticket(conn, t_id)
        assert tkt_done["status"] == "DONE"

        # 6. Swarm memeriksa tiket downstream -> tiket kedua (Build / @fe) otomatis jadi READY
        unblocked = await swarm.check_and_update_dependencies(conn, project_id)
        assert unblocked == 1

        cur = await conn.execute(
            "SELECT status, assigned_role_id FROM corporate_tickets WHERE project_id = ? AND id != ?",
            (project_id, t_id),
        )
        rows = await cur.fetchall()
        ready_downstream = [r for r in rows if r["status"] == "READY"]
        assert len(ready_downstream) == 1
        build_ticket_id = f"tkt_{project_id}_build"

        # 7. Ajukan Pull Request untuk pekerjaan build
        pr = await pr_repo.create_pr(
            conn=conn,
            pr_id=f"pr_{project_id}",
            project_id=project_id,
            ticket_id=build_ticket_id,
            author_role_id="role_fe",
            diff_content="+ export const VideoEditor = () => { return <Canvas />; };",
        )
        assert pr["status"] == "OPEN"

        # 8. Siklus Quorum Gate Review:
        # Review 1 oleh QA: APPROVED -> Quorum not met yet (1 < 2)
        rev1 = await pr_quorum_engine.submit_review(
            conn=conn,
            pr_id=pr["id"],
            reviewer_role_id="role_qa",
            verdict="APPROVED",
            security_score=100,
            comments=["Unit tests 100% pass."],
        )
        assert rev1["quorum_met"] is False
        assert rev1["status"] == "OPEN"

        # Review 2 oleh Security: APPROVED -> Quorum met (2 >= 2) -> Status APPROVED!
        rev2 = await pr_quorum_engine.submit_review(
            conn=conn,
            pr_id=pr["id"],
            reviewer_role_id="role_sec_eng",
            verdict="APPROVED",
            security_score=98,
            comments=["Security audit passed."],
        )
        assert rev2["quorum_met"] is True
        assert rev2["status"] == "APPROVED"

        pr_approved = await pr_repo.get_pr(conn, pr["id"])
        assert pr_approved["status"] == "APPROVED"
        flight_recorder.record_step(project_id, "role_sec_eng", "PR_APPROVED_QUORUM", rev2)

        # 9. Verifikasi Flight Recorder
        logs = flight_recorder.get_flight_log(project_id)
        assert len(logs) >= 3
        events = [l["event_type"] for l in logs]
        assert "PROJECT_DEPLOYED" in events
        assert "HOLD_TICKET_TRIGGERED" in events
        assert "PR_APPROVED_QUORUM" in events
