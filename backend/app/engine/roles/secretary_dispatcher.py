"""
Executive Personal Secretary & 3-Gear Command Dispatcher Subsystem (@secretary).
Menegakkan spesifikasi Secretary-Role.md:
- Gigi 1: Fast-Path Direct Answer & Isolasi Memori Personal (project_id = 'personal').
- Gigi 2: Ad-Hoc Expert Consultation via mention_relay.py & builtin:consult_role.
- Gigi 3: Direct Project & Ticket Creation (Inisiasi Swarm via DAG Runbook).
- Kurator Perkakas: Delegasi perakitan tool baru ke @tool_builder.
"""

from datetime import datetime, timezone
import json
import re
from typing import Any, Dict, List, Optional
import uuid
import aiosqlite

from app.core.logger import logger
from app.db.repos.project_repo import create_project, create_runbook
from app.engine.orchestrator.event_bus import corporate_event_bus
from app.engine.orchestrator.runbook_dag import runbook_dag_engine
from app.engine.roles.mention_relay import dispatch_scoped_mention, extract_mention_handles


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SecretaryDispatcher:
    """Komandan Omnichannel dan Jembatan Eksekutif Founder (@secretary)."""

    async def dispatch_command(
        self,
        conn: aiosqlite.Connection,
        user_prompt: str,
        founder_id: str = "founder",
    ) -> Dict[str, Any]:
        """Memproses instruksi Founder dan memilih gear transmisi yang paling hemat token."""
        lower_prompt = user_prompt.lower()

        # 1. Deteksi Gigi 3: Perintah Inisiasi Proyek / Bisnis Baru
        project_keywords = ["bikin proyek", "buat proyek", "bikin project", "buat project", "landing page", "saas"]
        if any(kw in lower_prompt for kw in project_keywords):
            return await self.gear_3_project_deployment(conn, user_prompt, founder_id)

        # 2. Deteksi Gigi 2: Konsultasi Pakar Ad-Hoc ke Peran Tertentu
        handles = extract_mention_handles(user_prompt)
        consult_keywords = ["tanya", "tanyakan", "konsultasi", "evaluasi", "pendapat"]
        if handles or any(kw in lower_prompt for kw in consult_keywords):
            target_handle = handles[0] if handles else "@cto"
            return await self.gear_2_expert_consultation(conn, target_handle, user_prompt, founder_id)

        # 3. Default ke Gigi 1: Personal Assistant Fast-Path Companion
        return await self.gear_1_personal_assistant(conn, user_prompt, founder_id)

    async def gear_1_personal_assistant(
        self,
        conn: aiosqlite.Connection,
        prompt: str,
        founder_id: str = "founder",
    ) -> Dict[str, Any]:
        """Gigi 1: Jawaban kilat 1-turn, 0-swarm overhead, memori personal terisolasi."""
        memo_id = f"wis_personal_{uuid.uuid4().hex[:8]}"
        now_str = _now_iso()

        # Simpan ke corporate_wisdom dengan label project_id = 'personal'
        await conn.execute(
            """
            INSERT INTO corporate_wisdom 
            (id, project_id, title, content, category, embedding_blob, created_at)
            VALUES (?, 'personal', 'Memo Personal Founder', ?, 'personal_memory', X'', ?)
            """,
            (memo_id, prompt, now_str),
        )
        await conn.commit()

        logger.info(f"[Secretary] Gigi 1 dieksekusi: Memo personal dicatat ke corporate_wisdom [{memo_id}].")
        return {
            "gear_selected": 1,
            "mode": "FAST_PATH_PERSONAL",
            "reply": f"Siap Pak/Bu, catatan Anda telah tersimpan rapi: '{prompt}'",
            "personal_memory_isolated": True,
        }

    async def gear_2_expert_consultation(
        self,
        conn: aiosqlite.Connection,
        target_role_handle: str,
        question: str,
        founder_id: str = "founder",
    ) -> Dict[str, Any]:
        """Gigi 2: Konsultasi ad-hoc ke 1 pakar spesialis via mention_relay tanpa memicu War Room."""
        dispatched = await dispatch_scoped_mention(
            conn=conn,
            project_id="executive_consult",
            raw_content=question,
            sender_id="role_secretary",
        )

        logger.info(f"[Secretary] Gigi 2 dieksekusi: Mengarahkan kueri ke {target_role_handle}.")
        return {
            "gear_selected": 2,
            "mode": "EXPERT_CONSULTATION",
            "consulted_role": target_role_handle,
            "reply": f"Pertanyaan Anda telah diteruskan ke {target_role_handle}. Saya akan segera merangkum jawabannya.",
            "scoped_dispatched": len(dispatched) > 0,
        }

    async def gear_3_project_deployment(
        self,
        conn: aiosqlite.Connection,
        prompt: str,
        founder_id: str = "founder",
    ) -> Dict[str, Any]:
        """Gigi 3: Pembuatan proyek baru, registrasi runbook DAG, dan inisiasi tiket Kanban."""
        proj_id = f"proj_{uuid.uuid4().hex[:8]}"
        archetype = "WEB_SAAS"
        if "android" in prompt.lower():
            archetype = "ANDROID_APP"
        elif "flutter" in prompt.lower():
            archetype = "FLUTTER_APP"

        # 1. Buat Proyek
        proj = await create_project(
            conn=conn,
            id=proj_id,
            name="New Venture Product",
            founder_vision=prompt,
            product_archetype=archetype,
        )

        # 2. Daftarkan Baseline 3-Stage Runbook
        runbook_id = f"rb_{proj_id}"
        stages = [
            {"id": "discovery", "name": "Market & Product Discovery", "assigned_role_handle": "@pm", "dependencies": []},
            {"id": "build", "name": "Core Implementation", "assigned_role_handle": "@fe", "dependencies": ["discovery"]},
            {"id": "qa", "name": "Quality & Security Assurance", "assigned_role_handle": "@qa", "dependencies": ["build"]},
        ]
        await create_runbook(conn, runbook_id, "Baseline 3-Phase", "Auto-generated by @secretary", stages)

        # 3. Kompilasi tiket ke papan Kanban
        tickets = await runbook_dag_engine.compile_runbook_to_tickets(conn, proj_id, runbook_id)

        # 4. Siarkan pengumuman proyek baru ke stream All & Execution
        await corporate_event_bus.publish(
            conn=conn,
            project_id=proj_id,
            stream_category="EXECUTION_HANDOFFS",
            event_type="PROJECT_CREATED",
            content=f"Proyek baru [{proj_id}] diinisiasi oleh @secretary berdasarkan instruksi Founder.",
            sender_role_id="role_secretary",
            metadata={"project_id": proj_id, "tickets_count": len(tickets)},
        )

        logger.info(f"[Secretary] Gigi 3 dieksekusi: Proyek [{proj_id}] dengan {len(tickets)} tiket berhasil dibuat.")
        return {
            "gear_selected": 3,
            "mode": "SWARM_DEPLOYMENT",
            "project_id": proj_id,
            "tickets_created": len(tickets),
            "reply": f"Proyek [{proj_id}] ({archetype}) telah berhasil dibuat dan {len(tickets)} tiket terdaftar di papan Kanban.",
        }

    async def delegate_to_tool_builder(
        self,
        conn: aiosqlite.Connection,
        tool_request_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Mendelegasikan sintesis perkakas baru ke agen on-demand @tool_builder."""
        req_approval = bool(tool_request_spec.get("requires_human_approval", 0))

        if req_approval:
            # Eskalasi ke Founder via CEO_DECISION_GATES
            await corporate_event_bus.publish(
                conn=conn,
                project_id="system",
                stream_category="CEO_DECISION_GATES",
                event_type="TOOL_BUILD_GATE",
                content=f"Permintaan perkakas baru berisiko '{tool_request_spec.get('display_name')}' membutuhkan persetujuan CEO.",
                sender_role_id="role_secretary",
                metadata=tool_request_spec,
            )

        logger.info(f"[Secretary] Pendelegasian tool '{tool_request_spec.get('tool_id')}' ke @tool_builder selesai.")
        return {
            "status": "QUEUED_FOR_BUILDER",
            "tool_spec": tool_request_spec,
            "escalated_to_ceo_gate": req_approval,
        }


secretary_dispatcher = SecretaryDispatcher()
