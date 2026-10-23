"""
Unit Tests for Orchestrator Core Primitives: FileLockManager & CorporateEventBus.
Menegakkan Invarian Suci 1 (0-Token Idle Event Bus) dan Anti-Race-Condition Path Lock.
"""

import asyncio
from pathlib import Path
import pytest
import aiosqlite

from app.db.session import get_db_connection
from app.engine.orchestrator.file_lock_manager import FileLockManager
from app.engine.orchestrator.event_bus import CorporateEventBus


@pytest.mark.asyncio
async def test_file_lock_manager_mutex_and_normalization():
    """Memastikan path locking bekerja pada level proyek dan dinormalisasi secara deterministik."""
    flm = FileLockManager()
    project_id = "proj_test_lock"
    
    # 1. Normalisasi: "./lib/../lib/main.dart" vs "lib/main.dart" harus mengunci resource yang sama
    async with flm.lock(project_id, "lib/main.dart"):
        acquired_second = False

        async def try_acquire():
            nonlocal acquired_second
            async with flm.lock(project_id, "./lib/../lib/main.dart"):
                acquired_second = True

        task = asyncio.create_task(try_acquire())
        await asyncio.sleep(0.05)
        # Lock kedua harus terblokir saat lock pertama masih dipegang
        assert not acquired_second

    # Setelah lock pertama lepas, lock kedua berhasil didapat
    await asyncio.wait_for(task, timeout=1.0)
    assert acquired_second


@pytest.mark.asyncio
async def test_file_lock_manager_release_all():
    """Memastikan release_all_project_locks melepaskan seluruh kunci terkait proyek."""
    flm = FileLockManager()
    project_id = "proj_test_rel_all"

    await flm.acquire(project_id, "file_a.py")
    await flm.acquire(project_id, "file_b.py")

    released_count = flm.release_all_project_locks(project_id)
    assert released_count >= 2

    # Kunci harus sudah bisa diambil kembali tanpa terblokir
    acquired = False
    async with flm.lock(project_id, "file_a.py"):
        acquired = True
    assert acquired is True


@pytest.mark.asyncio
async def test_corporate_event_bus_4_stream_routing():
    """Memastikan event bus menyaring pesan ke 4 channel stream dan menyimpan log ke corporate_messages."""
    bus = CorporateEventBus()
    project_id = "proj_bus_test"

    q_all = await bus.subscribe(project_id, category=None)
    q_exec = await bus.subscribe(project_id, category="EXECUTION_HANDOFFS")
    q_ceo = await bus.subscribe(project_id, category="CEO_DECISION_GATES")
    q_lounge = await bus.subscribe(project_id, category="OASIS_LOUNGE")

    async with get_db_connection() as conn:
        # Publish event ke EXECUTION_HANDOFFS
        msg_payload = await bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="EXECUTION_HANDOFFS",
            event_type="TASK_CLAIMED",
            content="Ticket tkt_01 claimed by @fe",
            sender_role_id="role_fe",
            metadata={"ticket_id": "tkt_01"},
        )
        assert msg_payload["id"] is not None

        # Verifikasi penerimaan queue
        evt_all = await asyncio.wait_for(q_all.get(), timeout=1.0)
        assert evt_all["event_type"] == "TASK_CLAIMED"
        assert evt_all["stream_category"] == "EXECUTION_HANDOFFS"

        evt_exec = await asyncio.wait_for(q_exec.get(), timeout=1.0)
        assert evt_exec["content"] == "Ticket tkt_01 claimed by @fe"

        # q_ceo dan q_lounge tidak boleh menerima pesan EXECUTION_HANDOFFS
        assert q_ceo.empty()
        assert q_lounge.empty()

        # Publish event ke CEO_DECISION_GATES
        await bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="CEO_DECISION_GATES",
            event_type="CIRCUIT_BREAKER_TRIGGERED",
            content="Discussion limit reached on tkt_02",
            sender_role_id="system",
        )
        evt_ceo = await asyncio.wait_for(q_ceo.get(), timeout=1.0)
        assert evt_ceo["event_type"] == "CIRCUIT_BREAKER_TRIGGERED"

    await bus.unsubscribe(project_id, q_all)
    await bus.unsubscribe(project_id, q_exec)
    await bus.unsubscribe(project_id, q_ceo)
    await bus.unsubscribe(project_id, q_lounge)
