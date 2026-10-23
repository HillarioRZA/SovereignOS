"""
Unit Tests for Delegation Tree and Autonomous Role Spawner.
Mematuhi Foreign Key Constraints dan Invarian Suci 6 (100% Slug-Free Dynamic RBAC).
"""

import json
import os
import tempfile
import pytest
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.engine.orchestrator.delegation_tree import delegation_tree
from app.engine.roles.role_spawner import role_spawner


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


async def _seed_delegation_parents(conn, project_id: str):
    await conn.execute(
        "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_del', 'Engineering', 'engineering', 'Core Dev')"
    )
    for r_id, handle in [("role_lead", "@tech_lead"), ("role_fe_dev", "@fe_dev")]:
        await conn.execute(
            """
            INSERT OR IGNORE INTO corporate_roles 
            (id, division_id, handle_mention, name, job_description, persona_prompt, system_prompt_template)
            VALUES (?, 'div_del', ?, 'Role', 'Desc', 'Soul', 'SOP')
            """,
            (r_id, handle),
        )
    await conn.execute(
        "INSERT OR IGNORE INTO projects (id, name, founder_vision, product_archetype) VALUES (?, 'Delegation Project', 'Vision', 'WEB_SAAS')",
        (project_id,),
    )
    # Insert parent ticket
    await conn.execute(
        """
        INSERT OR IGNORE INTO corporate_tickets 
        (id, project_id, assigned_role_id, title, description, acceptance_criteria, status)
        VALUES ('tkt_parent_main', ?, 'role_lead', 'Parent Epic', 'Desc', 'AC', 'IN_PROGRESS')
        """,
        (project_id,),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_delegation_tree_subtask_creation_and_blocking(temp_db):
    """Menguji pendelegasian subtiket dan pemblokiran tiket induk hingga subtiket selesai."""
    async with get_db_connection(temp_db) as conn:
        proj_id = "p_delegation_test"
        await _seed_delegation_parents(conn, proj_id)

        # 1. Delegasikan subtugas
        subtask = await delegation_tree.delegate_subtask(
            conn=conn,
            project_id=proj_id,
            parent_ticket_id="tkt_parent_main",
            assigned_role_id="role_fe_dev",
            title="Implement Navbar Component",
            description="Create responsive navbar with tailwind",
            acceptance_criteria="Passes visual tests",
        )
        assert subtask["parent_ticket_id"] == "tkt_parent_main"
        assert subtask["status"] == "READY"
        assert subtask["assigned_role_id"] == "role_fe_dev"

        # 2. Cek apakah subtugas sudah selesai (belum)
        is_completed = await delegation_tree.check_subtasks_completed(conn, "tkt_parent_main")
        assert is_completed is False

        # 3. Selesaikan subtugas -> status DONE
        await conn.execute("UPDATE corporate_tickets SET status = 'DONE' WHERE id = ?", (subtask["id"],))
        await conn.commit()

        # 4. Sekarang seluruh subtugas harus sudah selesai
        is_completed_now = await delegation_tree.check_subtasks_completed(conn, "tkt_parent_main")
        assert is_completed_now is True


@pytest.mark.asyncio
async def test_role_spawner_autonomous_hiring(temp_db):
    """Menguji perekrutan otonom peran spesialis baru tanpa modifikasi kode Python."""
    async with get_db_connection(temp_db) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_spawner', 'Web3', 'web3', 'Blockchain')"
        )
        await conn.commit()

        new_role = await role_spawner.spawn_role(
            conn=conn,
            division_id="div_spawner",
            handle_mention="@solana_dev",
            name="Solana Rust Core Engineer",
            job_description="Builds Anchor smart contracts & SPL tokens",
            persona_prompt="You are a senior Solana Rust blockchain engineer.",
            system_prompt_template="Follow Anchor best practices and strictly adhere to PDA safety.",
            tool_permissions=["builtin:read_file", "ptc:execute_code"],
        )
        assert new_role["id"].startswith("role_")
        assert new_role["handle_mention"] == "@solana_dev"
        assert new_role["is_autonomous_spawned"] == 1
        assert "builtin:read_file" in new_role["tool_permissions_json"]

        # Verifikasi peran dapat ditarik kembali dari database
        cur = await conn.execute("SELECT * FROM corporate_roles WHERE handle_mention = '@solana_dev'")
        row = await cur.fetchone()
        assert row is not None
        assert row["name"] == "Solana Rust Core Engineer"
