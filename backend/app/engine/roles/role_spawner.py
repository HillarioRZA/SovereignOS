"""
Autonomous Role Spawner Subsystem.
Menegakkan Invarian Suci 6: 100% Slug-Free & Dynamic Database-Driven Roles.
Memungkinkan sistem melahirkan peran spesialis baru secara on-demand langsung di DB
tanpa memerlukan modifikasi atau deployment ulang kode sumber Python.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import uuid
import aiosqlite

from app.core.logger import logger
from app.engine.orchestrator.event_bus import corporate_event_bus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RoleSpawner:
    """Mesin perekrutan peran otonom (Autonomous Hiring) langsung ke tabel corporate_roles."""

    async def spawn_role(
        self,
        conn: aiosqlite.Connection,
        division_id: str,
        handle_mention: str,
        name: str,
        job_description: str,
        persona_prompt: str,
        system_prompt_template: str,
        tool_permissions: Optional[List[str]] = None,
        model_provider: str = "anthropic",
        model_name: str = "claude-3-7-sonnet",
        temperature: float = 0.2,
        thinking_level: str = "medium",
        token_budget_limit: int = 350000,
    ) -> Dict[str, Any]:
        """Melahirkan peran baru langsung ke tabel corporate_roles dengan ID acak role_{uuid}."""
        role_id = f"role_{uuid.uuid4().hex[:8]}"
        handle = handle_mention if handle_mention.startswith("@") else f"@{handle_mention}"
        tools_json = json.dumps(tool_permissions or ["builtin:read_file"])
        now_str = _now_iso()

        query = """
        INSERT INTO corporate_roles (
            id, division_id, handle_mention, name, job_description,
            persona_prompt, system_prompt_template, model_provider,
            model_name, fallback_models_json, temperature, thinking_level,
            tool_permissions_json, token_budget_limit, is_autonomous_spawned,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, 1, ?)
        RETURNING *;
        """
        cur = await conn.execute(
            query,
            (
                role_id,
                division_id,
                handle,
                name,
                job_description,
                persona_prompt,
                system_prompt_template,
                model_provider,
                model_name,
                temperature,
                thinking_level,
                tools_json,
                token_budget_limit,
                now_str,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()
        spawned_role = dict(row) if row else {}

        # Siarkan pengumuman peran baru ke event bus (Lounge stream)
        await corporate_event_bus.publish(
            conn=conn,
            project_id="system",
            stream_category="OASIS_LOUNGE",
            event_type="ROLE_SPAWNED",
            content=f"Peran baru {handle} ({name}) berhasil dilahirkan secara otonom di divisi [{division_id}].",
            sender_role_id="system",
            metadata={"role_id": role_id, "handle": handle},
        )

        logger.info(f"[RoleSpawner] Peran baru [{role_id}] {handle} ({name}) sukses didaftarkan ke DB.")
        return spawned_role


role_spawner = RoleSpawner()
