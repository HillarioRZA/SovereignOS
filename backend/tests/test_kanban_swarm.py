"""
Unit Tests for Autonomous Kanban Swarm Runner (kanban_swarm.py).
Mematuhi Foreign Key Constraints dan Invarian Suci 9 (Atomic Claim & Heartbeat Lease).
"""

import os
import tempfile
import json
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.engine.orchestrator.kanban_swarm import AutonomousKanbanSwarm


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


async def _seed_swarm_parents(conn, project_id: str):
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_sw', 'Swarm Div', 'swarm', 'Dev')"
    )
    for r_id, handle in [("role_sw_fe", "@fe"), ("role_sw_qa", "@qa")]:
        await conn.execute(
            """
            INSERT OR IGNORE INTO corporate_roles 
            (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
            VALUES (?, 'div_sw', ?, 'Role', 'Desc', 'Soul', 'SOP')
            """,
            (r_id, handle),
        )
    await conn.execute(
        "INSERT OR IGNORE INTO projects (id, name, founder_vision, product_archetype) VALUES (?, 'Swarm Project', 'Vision', 'WEB_SAAS')",
        (project_id,),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_kanban_swarm_atomic_claim_and_dependency_progression(temp_db):
    """Menguji klaim atomik tiket READY dan transisi tiket BACKLOG menjadi READY saat dependensi selesai."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "p_swarm_01"
        await _seed_swarm_parents(conn, proj_id)

        # Tiket 1: READY
        await conn.execute(
            """
            INSERT INTO corporate_tickets 
            (id, project_id, assigned_role_id, title, description, acceptance_criteria, status, priority, dependencies_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("tkt_sw_1", proj_id, "role_sw_fe", "Task 1", "Desc", "AC", "READY", "HIGH", "[]"),
        )
        # Tiket 2: BACKLOG (tergantung tkt_sw_1)
        await conn.execute(
            """
            INSERT INTO corporate_tickets 
            (id, project_id, assigned_role_id, title, description, acceptance_criteria, status, priority, dependencies_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("tkt_sw_2", proj_id, "role_sw_qa", "Task 2 QA", "Desc", "AC", "BACKLOG", "MEDIUM", json.dumps(["tkt_sw_1"])),
        )
        await conn.commit()

        swarm = AutonomousKanbanSwarm(max_concurrency=2)

        # 1. Scan and claim tickets
        claimed = await swarm.scan_and_claim_tickets(conn, proj_id)
        assert len(claimed) == 1
        assert claimed[0]["id"] == "tkt_sw_1"
        assert claimed[0]["status"] == "IN_PROGRESS"
        assert claimed[0]["lease_owner"] is not None

        # 2. Tandai tkt_sw_1 sebagai DONE
        await conn.execute("UPDATE corporate_tickets SET status = 'DONE' WHERE id = 'tkt_sw_1'")
        await conn.commit()

        # 3. Cek dependensi tiket downstream
        unblocked_count = await swarm.check_and_update_dependencies(conn, proj_id)
        assert unblocked_count == 1

        cur = await conn.execute("SELECT status FROM corporate_tickets WHERE id = 'tkt_sw_2'")
        row = await cur.fetchone()
        assert row["status"] == "READY"


@pytest.mark.asyncio
async def test_kanban_swarm_reclaim_expired_leases(temp_db):
    """Memastikan tiket IN_PROGRESS yang masa lease-nya kedaluwarsa ditarik kembali menjadi READY."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "p_swarm_lease_test"
        await _seed_swarm_parents(conn, proj_id)

        # Insert tiket dengan lease kedaluwarsa di masa lalu
        await conn.execute(
            """
            INSERT INTO corporate_tickets 
            (id, project_id, assigned_role_id, title, description, acceptance_criteria, status, lease_owner, lease_expires_at)
            VALUES (?, ?, ?, ?, ?, ?, 'IN_PROGRESS', 'worker_dead', '2020-01-01T00:00:00')
            """,
            ("tkt_sw_expired", proj_id, "role_sw_fe", "Expired Task", "Desc", "AC"),
        )
        await conn.commit()

        swarm = AutonomousKanbanSwarm()
        reclaimed = await swarm.reclaim_expired_leases(conn, proj_id)
        assert reclaimed == 1

        cur = await conn.execute("SELECT status, lease_owner FROM corporate_tickets WHERE id = 'tkt_sw_expired'")
        row = await cur.fetchone()
        assert row["status"] == "READY"
        assert row["lease_owner"] is None
