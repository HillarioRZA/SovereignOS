"""
Dynamic Node: Instansiasi Agen Polimorfik dari Basis Data.
Menegakkan Invarian Suci 6: 100% Slug-Free & Database-Driven RBAC.
Setiap agen diinstansiasi secara dinamis dari tabel corporate_roles tanpa hardcoding kode Python.
"""

from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.logger import logger
from app.db.repos.role_repo import get_role_by_id, get_role_by_handle
from app.engine.turn.turn_facade import run_turn_cycle, TurnCycleResult
from app.gateway.model_router import SovereignModelRouter


class DynamicNode:
    """Instansi agen polimorfik yang merepresentasikan peran korporat aktif."""

    def __init__(self, role_id: str, role_data: Dict[str, Any]) -> None:
        self.role_id = role_id
        self.name = role_data.get("name", "Unknown Role")
        self.handle_mention = role_data.get("handle_mention", "@agent")
        self.model_provider = role_data.get("model_provider", "anthropic")
        self.model_name = role_data.get("model_name", "claude-3-7-sonnet")
        self.persona_prompt = role_data.get("persona_prompt", "")
        self.sop_template = role_data.get("system_prompt_template", "")
        self.raw_data = role_data

    @classmethod
    async def from_role_id(cls, conn: aiosqlite.Connection, role_id: str) -> Optional["DynamicNode"]:
        """Membuat instance DynamicNode berdasarkan ID peran di database."""
        role_data = await get_role_by_id(conn, role_id)
        if not role_data:
            return None
        return cls(role_id=role_id, role_data=role_data)

    @classmethod
    async def from_handle(cls, conn: aiosqlite.Connection, handle: str) -> Optional["DynamicNode"]:
        """Membuat instance DynamicNode berdasarkan handle @mention (misal: '@cto')."""
        role_data = await get_role_by_handle(conn, handle)
        if not role_data:
            return None
        return cls(role_id=role_data["id"], role_data=role_data)

    async def execute_turn(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        ticket_id: str,
        router: Optional[SovereignModelRouter] = None,
        turn_count: int = 1,
        interrupt_flag: bool = False,
        simulate_critic_pass: bool = False,
    ) -> TurnCycleResult:
        """Menjalankan 1 giliran kerja agen menggunakan 10-Phase Turn Loop."""
        logger.info(f"[DynamicNode] Agen {self.handle_mention} ({self.name}) memulai eksekusi tiket {ticket_id}.")
        return await run_turn_cycle(
            conn=conn,
            project_id=project_id,
            ticket_id=ticket_id,
            role_id=self.role_id,
            router=router,
            turn_count=turn_count,
            interrupt_flag=interrupt_flag,
            simulate_critic_pass=simulate_critic_pass,
        )
