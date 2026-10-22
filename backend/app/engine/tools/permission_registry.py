"""
Tool Permission Registry & RBAC Verification Engine.
Mengelola pendaftaran perkakas bawaan dan verifikasi hak akses per peran.
"""

from typing import Any, Dict, List
import aiosqlite

from app.db.repos.tool_repo import register_tool_permission, get_tool_permission
from app.core.logger import logger

# Definisi skema perkakas inti sistem
BASELINE_TOOLS: List[Dict[str, Any]] = [
    {
        "tool_id": "builtin:read_file",
        "namespace": "builtin",
        "display_name": "Read File",
        "description": "Membaca isi berkas dari sistem berkas proyek.",
        "risk_tier": 1,
        "requires_human_approval": 0,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path relatif berkas yang ingin dibaca."}
            },
            "required": ["file_path"],
        },
    },
    {
        "tool_id": "builtin:write_file",
        "namespace": "builtin",
        "display_name": "Write File",
        "description": "Menulis atau membuat berkas baru pada proyek.",
        "risk_tier": 2,
        "requires_human_approval": 0,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path berkas tujuan."},
                "content": {"type": "string", "description": "Isi konten yang akan ditulis."}
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "tool_id": "builtin:list_directory",
        "namespace": "builtin",
        "display_name": "List Directory",
        "description": "Melihat daftar berkas dan folder dalam suatu direktori.",
        "risk_tier": 1,
        "requires_human_approval": 0,
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "Path direktori (default: '.')"}
            },
            "required": [],
        },
    },
    {
        "tool_id": "builtin:search_files",
        "namespace": "builtin",
        "display_name": "Search Files",
        "description": "Mencari pola teks atau nama berkas di seluruh proyek.",
        "risk_tier": 1,
        "requires_human_approval": 0,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Kata kunci pencarian."},
                "file_pattern": {"type": "string", "description": "Pola ekstensi berkas opsional (misal: *.py)"}
            },
            "required": ["query"],
        },
    },
    {
        "tool_id": "ptc:execute_code",
        "namespace": "ptc",
        "display_name": "Execute Code (PTC)",
        "description": "Mengeksekusi skrip Python di dalam sandbox untuk tugas programmatic berulang.",
        "risk_tier": 2,
        "requires_human_approval": 0,
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Kode sumber Python lengkap yang akan dieksekusi."}
            },
            "required": ["code"],
        },
    },
]


async def seed_baseline_tools(conn: aiosqlite.Connection) -> int:
    """Mendaftarkan seluruh perkakas bawaan ke basis data."""
    count = 0
    for t in BASELINE_TOOLS:
        await register_tool_permission(
            conn=conn,
            tool_id=t["tool_id"],
            namespace=t["namespace"],
            display_name=t["display_name"],
            description=t["description"],
            parameters_json_schema=t["parameters"],
            risk_tier=t["risk_tier"],
            requires_human_approval=t["requires_human_approval"],
        )
        count += 1
    logger.info(f"{count} perkakas bawaan berhasil didaftarkan ke tool_permissions_registry.")
    return count


async def check_role_has_tool_permission(
    conn: aiosqlite.Connection,
    role_allowed_tools: List[str],
    tool_id: str,
) -> bool:
    """Memeriksa apakah peran memiliki izin memanggil tool_id ini."""
    # Wildcard permission support
    if "*" in role_allowed_tools or "all" in role_allowed_tools:
        return True
    if tool_id in role_allowed_tools:
        return True
    
    # Cek apakah terdaftar di namespace yang diizinkan (misal: 'builtin:*')
    ns = tool_id.split(":")[0] if ":" in tool_id else ""
    if f"{ns}:*" in role_allowed_tools:
        return True

    return False
