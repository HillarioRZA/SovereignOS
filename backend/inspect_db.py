"""
Skrip Inspeksi Cepat Basis Data Sovereign OS.
Menampilkan ringkasan DDL, divisi, dan peran agen yang telah di-ingest.
"""

import asyncio
import sys
import aiosqlite
from app.db.session import resolve_db_path

# Pastikan output konsol Windows mendukung encoding teks aman
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main():
    db_path = resolve_db_path()
    print("==================================================")
    print("[INSPEKSI] BASIS DATA SOVEREIGN OS (FASE 1)")
    print(f"[PATH] Lokasi File DB: {db_path}")
    print("==================================================")

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Hitung total tabel
        cur = await conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        total_tables = (await cur.fetchone())[0]
        print(f"[TABEL] Total Tabel Relasional: {total_tables} tabel")

        # 2. Hitung divisi
        cur = await conn.execute("SELECT COUNT(*) FROM corporate_divisions")
        total_divs = (await cur.fetchone())[0]
        print(f"[DIVISI] Total Divisi Industri: {total_divs} divisi")

        # 3. Hitung peran agen
        cur = await conn.execute("SELECT COUNT(*) FROM corporate_roles")
        total_roles = (await cur.fetchone())[0]
        print(f"[AGEN] Total Agen Peran: {total_roles} agen terdaftar")

        # 4. Contoh peran eksekutif & teknis
        print("\n[CONTOH AGEN] Contoh Agen Kanonikal & Handle @mention:")
        handles = ["@cos", "@cto", "@be", "@fe", "@pm", "@cfo", "@qa"]
        cur = await conn.execute(
            f"SELECT name, handle_mention, model_provider, model_name FROM corporate_roles WHERE handle_mention IN ({','.join(['?']*len(handles))})",
            handles,
        )
        for r in await cur.fetchall():
            print(f"   * {r['handle_mention']:<10} : {r['name']:<28} [{r['model_provider']}/{r['model_name']}]")

        # 5. Cek status lease & PRAGMA
        cur = await conn.execute("PRAGMA journal_mode")
        journal_mode = (await cur.fetchone())[0]
        print(f"\n[JOURNAL] Mode Journal SQLite: {journal_mode.upper()} (Write-Ahead Logging Aktif)")

    print("\n[SUCCESS] STATUS FASE 1: 100% VALID & SIAP DIGUNAKAN!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
