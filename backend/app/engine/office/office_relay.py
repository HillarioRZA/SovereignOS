"""
Office Relay Subsystem.
Menghubungkan event pemikiran, screen-share, dan telemetri agen ke antarmuka /office.
Menegakkan Invarian Suci 1: 0-Token Saat Idle (Murni Event-Driven).
"""

from typing import Any, Dict, Optional
import aiosqlite

from app.core.logger import logger
from app.db.repos.ticket_repo import update_screenshare_telemetry
from app.engine.orchestrator.event_bus import corporate_event_bus


class OfficeRelay:
    """Relay telemetri agen real-time untuk feed Live Agent Screen-Share Pane."""

    async def emit_screenshare_telemetry(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        ticket_id: str,
        role_handle: str,
        status_bubble: str,
        active_file_path: Optional[str] = None,
        live_scratchpad: Optional[str] = None,
        live_diff_preview: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Memperbarui telemetri di tabel corporate_tickets dan memancarkan event ke stream ALL."""
        # 1. Update ke SQLite WAL
        await update_screenshare_telemetry(
            conn=conn,
            ticket_id=ticket_id,
            active_file_path=active_file_path,
            live_scratchpad_text=live_scratchpad,
            status_bubble_text=status_bubble,
        )

        telemetry_payload = {
            "ticket_id": ticket_id,
            "role_handle": role_handle,
            "status_bubble": status_bubble,
            "active_file_path": active_file_path,
            "live_scratchpad": live_scratchpad,
            "live_diff_preview": live_diff_preview,
        }

        # 2. Siarkan ke event bus tanpa polling LLM (0-Token Idle Overhead)
        await corporate_event_bus.publish(
            conn=conn,
            project_id=project_id,
            stream_category="ALL",
            event_type="SCREEN_SHARE_UPDATE",
            content=f"{role_handle}: {status_bubble}",
            sender_role_id=role_handle,
            metadata=telemetry_payload,
        )

        logger.debug(f"[OfficeRelay] Screen-share telemetry broadcasted for ticket [{ticket_id}].")
        return telemetry_payload


office_relay = OfficeRelay()
