"""
Repository Polimorfik untuk Peran Korporat (corporate_roles).
Menyediakan kueri peran, pencarian handle @mention, dan ekstraksi prompt 3-Layer.
"""

import json
from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.logger import logger


async def get_role_by_id(conn: aiosqlite.Connection, role_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil definisi peran lengkap berdasarkan ID unik."""
    cur = await conn.execute("SELECT * FROM corporate_roles WHERE id = ?", (role_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_role_by_handle(conn: aiosqlite.Connection, handle_mention: str) -> Optional[Dict[str, Any]]:
    """Mencari peran berdasarkan handle @mention (misal: '@cos', '@cto', '@fe')."""
    clean_handle = handle_mention.strip()
    if not clean_handle.startswith("@"):
        clean_handle = f"@{clean_handle}"
    cur = await conn.execute(
        "SELECT * FROM corporate_roles WHERE LOWER(handle_mention) = LOWER(?)",
        (clean_handle,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_roles_by_division(conn: aiosqlite.Connection, division_id: str) -> List[Dict[str, Any]]:
    """Mengambil seluruh peran di bawah satu divisi."""
    cur = await conn.execute(
        "SELECT * FROM corporate_roles WHERE division_id = ? ORDER BY name ASC",
        (division_id,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def list_all_roles(conn: aiosqlite.Connection) -> List[Dict[str, Any]]:
    """Mengambil seluruh daftar peran korporat terdaftar."""
    cur = await conn.execute("SELECT * FROM corporate_roles ORDER BY name ASC")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def upsert_role(
    conn: aiosqlite.Connection,
    role_id: str,
    division_id: str,
    handle_mention: str,
    name: str,
    job_description: str,
    persona_prompt: str,
    system_prompt_template: str,
    model_provider: str = "anthropic",
    model_name: str = "claude-3-7-sonnet",
    fallback_models: Optional[List[str]] = None,
    temperature: float = 0.2,
    thinking_level: str = "medium",
    tool_permissions: Optional[List[str]] = None,
    token_budget_limit: int = 350000,
) -> None:
    """Menyimpan atau memperbarui data peran secara idempoten."""
    fallbacks_json = json.dumps(fallback_models or [])
    tools_json = json.dumps(tool_permissions or [])

    await conn.execute(
        """
        INSERT INTO corporate_roles (
            id, division_id, handle_mention, name, job_description,
            persona_prompt, system_prompt_template, model_provider, model_name,
            fallback_models_json, temperature, thinking_level, tool_permissions_json,
            token_budget_limit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            division_id = excluded.division_id,
            handle_mention = excluded.handle_mention,
            name = excluded.name,
            job_description = excluded.job_description,
            persona_prompt = excluded.persona_prompt,
            system_prompt_template = excluded.system_prompt_template,
            model_provider = excluded.model_provider,
            model_name = excluded.model_name,
            fallback_models_json = excluded.fallback_models_json,
            temperature = excluded.temperature,
            thinking_level = excluded.thinking_level,
            tool_permissions_json = excluded.tool_permissions_json,
            token_budget_limit = excluded.token_budget_limit;
        """,
        (
            role_id, division_id, handle_mention, name, job_description,
            persona_prompt, system_prompt_template, model_provider, model_name,
            fallbacks_json, temperature, thinking_level, tools_json,
            token_budget_limit
        ),
    )
    await conn.commit()
