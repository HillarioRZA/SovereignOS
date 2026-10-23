"""
Unit Tests for Project Repository and Dynamic Runbook DAG Engine.
Mematuhi Foreign Key Constraints dan Invarian Suci 6 (DB-Driven DAG).
"""

import json
import os
import tempfile
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.db.repos.project_repo import (
    create_project,
    get_project,
    create_runbook,
    get_runbook,
)
from app.engine.orchestrator.runbook_dag import RunbookDAGEngine


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


async def _seed_roles_for_dag(conn):
    """Seed corporate_divisions and corporate_roles for DAG testing."""
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_dag', 'Dev', 'dev', 'Dev')"
    )
    roles = [
        ("role_dag_pm", "@pm", "PM Specialist"),
        ("role_dag_cto", "@cto", "CTO Specialist"),
        ("role_dag_fe", "@fe", "Frontend Specialist"),
        ("role_dag_be", "@be", "Backend Specialist"),
        ("role_dag_qa", "@qa", "QA Specialist"),
    ]
    for r_id, handle, name in roles:
        await conn.execute(
            """
            INSERT OR IGNORE INTO corporate_roles 
            (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
            VALUES (?, 'div_dag', ?, ?, 'Desc', 'Soul', 'SOP')
            """,
            (r_id, handle, name),
        )
    await conn.commit()


@pytest.mark.asyncio
async def test_project_repo_crud(temp_db):
    """Memastikan operasi CRUD repositori proyek dan runbook bekerja dengan benar."""
    async with get_db_connection(temp_db) as conn:
        p = await create_project(
            conn=conn,
            id="proj_repo_test_01",
            name="Sovereign AI Suite",
            founder_vision="Autonomous AI Studio",
            product_archetype="WEB_SAAS",
            active_sandbox_profile="profile-web-saas",
        )
        assert p["id"] == "proj_repo_test_01"
        assert p["status"] == "DISCOVERY"

        fetched = await get_project(conn, "proj_repo_test_01")
        assert fetched is not None
        assert fetched["name"] == "Sovereign AI Suite"

        stages = [
            {"id": "s_disc", "name": "Discovery", "assigned_role_handle": "@pm", "dependencies": []},
            {"id": "s_build", "name": "Build", "assigned_role_handle": "@fe", "dependencies": ["s_disc"]},
        ]
        rb = await create_runbook(
            conn=conn,
            id="rb_test_01",
            name="2-Phase Runbook",
            description="Simple 2-phase build",
            dag_stages=stages,
        )
        assert rb["id"] == "rb_test_01"

        fetched_rb = await get_runbook(conn, "rb_test_01")
        assert fetched_rb is not None
        assert len(json.loads(fetched_rb["dag_stages_json"])) == 2


@pytest.mark.asyncio
async def test_runbook_dag_compilation_and_dependencies(temp_db):
    """Memastikan kompilasi DAG menghasilkan tiket dengan status awal READY untuk akar DAG dan BACKLOG untuk downstream."""
    async with get_db_connection(temp_db) as conn:
        await _seed_roles_for_dag(conn)

        proj_id = "proj_dag_compile_test"
        await create_project(
            conn=conn,
            id=proj_id,
            name="Crypto Trader SaaS",
            founder_vision="Build autonomous trading bot",
            product_archetype="WEB_SAAS",
        )

        stages = [
            {"id": "discovery", "name": "Discovery & PRD", "assigned_role_handle": "@pm", "dependencies": []},
            {"id": "architecture", "name": "Architecture Design", "assigned_role_handle": "@cto", "dependencies": ["discovery"]},
            {"id": "frontend", "name": "Frontend Dashboard", "assigned_role_handle": "@fe", "dependencies": ["architecture"]},
            {"id": "backend", "name": "Backend Engine", "assigned_role_handle": "@be", "dependencies": ["architecture"]},
            {"id": "qa", "name": "QA Quorum Testing", "assigned_role_handle": "@qa", "dependencies": ["frontend", "backend"]},
        ]
        await create_runbook(
            conn=conn,
            id="rb_saas_full",
            name="Full 5-Stage SaaS",
            description="Standard flow",
            dag_stages=stages,
        )

        engine = RunbookDAGEngine()
        tickets = await engine.compile_runbook_to_tickets(conn, proj_id, "rb_saas_full")
        assert len(tickets) == 5

        status_by_stage = {t["id"].split(f"tkt_{proj_id}_")[1]: t["status"] for t in tickets}
        assert status_by_stage["discovery"] == "READY"
        assert status_by_stage["architecture"] == "BACKLOG"
        assert status_by_stage["frontend"] == "BACKLOG"
        assert status_by_stage["backend"] == "BACKLOG"
        assert status_by_stage["qa"] == "BACKLOG"

        # Verifikasi dependensi QA mengarah ke tiket frontend dan backend
        qa_ticket = next(t for t in tickets if t["id"] == f"tkt_{proj_id}_qa")
        qa_deps = json.loads(qa_ticket["dependencies_json"])
        assert f"tkt_{proj_id}_frontend" in qa_deps
        assert f"tkt_{proj_id}_backend" in qa_deps
