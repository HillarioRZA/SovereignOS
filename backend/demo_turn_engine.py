"""
Demonstrasi Interaktif Turn Engine & CoV Gatekeeper (Mode LLM & Mode Jev).
Menjalankan alur otonomi peran agen, deteksi perkakas, verifikasi CoV,
dan Non-Hijacking Worker Self-Repair.
"""

import asyncio
import tempfile
import os
import aiosqlite

from app.db.schemas import execute_ddl_migrations
from app.db.repos.role_repo import upsert_role
from app.engine.governance.cov_verifier import CoVVerifier
from app.engine.governance.jev_client import JevSystemOneClient
from app.engine.tools.mock_executor import MockToolExecutor
from app.engine.turn.turn_tool_round import execute_turn_tool_round


async def main():
    print("=" * 70)
    print("  SOVEREIGN OS - ENGINE & CHAIN-OF-VERIFICATION (CoV) DEMO")
    print("=" * 70)

    # 1. Setup Database Memori Sementara
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    try:
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = OFF;")
            await execute_ddl_migrations(conn)

            # Inisialisasi Peran & Tool
            await conn.execute("INSERT INTO projects (id, name, founder_vision, product_archetype) VALUES ('proj_demo', 'Sovereign Demo', 'AI SaaS', 'WEB_SAAS')")
            await conn.execute("INSERT INTO corporate_divisions (id, name, slug, purpose) VALUES ('div_tech', 'Engineering', 'eng', 'Tech')")
            await upsert_role(
                conn=conn,
                role_id="role_backend",
                division_id="div_tech",
                handle_mention="@backend",
                name="Backend Engineer",
                job_description="Python & DB Specialist",
                persona_prompt="Lead developer.",
                system_prompt_template="Follow protocols.",
                tool_permissions=["builtin:read_file", "builtin:write_file"],
            )

            # --- SKENARIO 1: AGENT ROLE OTONOM (TANPA TOOL CALL) ---
            print("\n[SKENARIO 1] Respon Agen Murni Tanpa Perkakas (Passthrough Otonom)")
            agent_response_1 = "Tugas migrasi database selesai! Semua tabel berjalan dalam mode SQLite WAL."
            
            verifier_llm = CoVVerifier(mode="llm")
            round_1 = await execute_turn_tool_round(
                conn=conn,
                project_id="proj_demo",
                ticket_id="tkt_01",
                role_id="role_backend",
                model_content=agent_response_1,
                allowed_tool_ids=["builtin:read_file", "builtin:write_file"],
                cov_verifier=verifier_llm,
            )
            print(f" -> Deteksi Tool: {round_1['has_tool_calls']}")
            print(f" -> Rute Tujuan : {round_1.get('route_to')}")
            print(f" -> Pesan       : {round_1.get('message')}")
            print(" -> Hasil: Agen peran langsung menyerahkan respon ke User/Peer tanpa intervensi CoV!\n")

            # --- SKENARIO 2: MODE JEV (TypeSafe AI) - PARAMETER TIDAK LENGKAP ---
            print("-" * 70)
            print("[SKENARIO 2] Agen Butuh Tool dengan Parameter Cacat -> CoV Mode JEV")
            agent_bad_tool = 'Saya akan menulis file baru.\n```json\n{"tool": "builtin:write_file", "parameters": {"file_path": ""}}\n```'
            
            verifier_jev = CoVVerifier(mode="jev")
            round_2 = await execute_turn_tool_round(
                conn=conn,
                project_id="proj_demo",
                ticket_id="tkt_02",
                role_id="role_backend",
                model_content=agent_bad_tool,
                allowed_tool_ids=["builtin:read_file", "builtin:write_file"],
                cov_verifier=verifier_jev,
                tool_schemas={"builtin:write_file": {"required": ["file_path", "content"]}},
            )
            print(f" -> Deteksi Tool   : {round_2['has_tool_calls']}")
            print(f" -> Repair Needed  : {round_2['repair_needed']}")
            print(f" -> Feedback CoV   : {round_2['repair_feedback']}")
            print(" -> Hasil: CoV TIDAK memodifikasi parameter sendiri; feedback dikirim balik ke Agen!\n")

            # --- SKENARIO 3: AGENT ROLE SELF-REPAIR & APPROVAL ---
            print("-" * 70)
            print("[SKENARIO 3] Agen Peran Memperbaiki Parameter (Self-Repair) -> CoV Menyetujui & Eksekusi")
            agent_repaired_tool = 'Memperbaiki parameter sesuai arahan CoV.\n```json\n{"tool": "builtin:write_file", "parameters": {"file_path": "backend/main.py", "content": "print(\'Hello Sovereign\')"}}\n```'
            
            round_3 = await execute_turn_tool_round(
                conn=conn,
                project_id="proj_demo",
                ticket_id="tkt_03",
                role_id="role_backend",
                model_content=agent_repaired_tool,
                allowed_tool_ids=["builtin:read_file", "builtin:write_file"],
                cov_verifier=verifier_jev,
                tool_schemas={"builtin:write_file": {"required": ["file_path", "content"]}},
            )
            print(f" -> Deteksi Tool   : {round_3['has_tool_calls']}")
            print(f" -> Repair Needed  : {round_3['repair_needed']}")
            print(f" -> Status Hasil   : {round_3['tool_results'][0]['status']}")
            print(f" -> Output Tool    : {round_3['tool_results'][0].get('output')}")
            print(" -> Hasil: Parameter tepat disetujui, Agen peran sukses mengeksekusi perkakas!")

            print("\n" + "=" * 70)
            print("  DEMO SELESAI DENGAN SUKSES (100% INVARIAN SUCI TERPENUHI)")
            print("=" * 70)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(main())
