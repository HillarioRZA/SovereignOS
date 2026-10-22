"""
Mention Relay: Pengarah Intervensi Terarah (@mention Isolation).
Menegakkan Invarian Suci 2: Scoped @mention Context Isolation.
Founder dapat mengirim instruksi ke @role tertentu tanpa mengotori context window agen lain.
"""

import re
from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.logger import logger
from app.db.repos.role_repo import get_role_by_handle
from app.db.repos.message_repo import insert_message


def extract_mention_handles(text: str) -> List[str]:
    """Mengekstraksi seluruh handle @mention dari teks (misal: ['@cto', '@fe'])."""
    raw_handles = re.findall(r"@([a-zA-Z0-9_\-]+)", text)
    return [f"@{h.lower()}" for h in raw_handles]


async def dispatch_scoped_mention(
    conn: aiosqlite.Connection,
    project_id: str,
    raw_content: str,
    sender_id: str = "founder",
    ticket_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Mem-parsing teks instruksi dan mengirimkannya secara terisolasi ke agen yang dimention."""
    handles = extract_mention_handles(raw_content)
    dispatched: List[Dict[str, Any]] = []

    if not handles:
        # Jika tidak ada @mention khusus, kirim sebagai pesan publik ke all stream
        msg_id = await insert_message(
            conn=conn,
            project_id=project_id,
            stream_category="GENERAL_THOUGHT",
            event_type="THOUGHT",
            content=raw_content,
            sender_role_id=sender_id,
            scoped_recipient_role_id=None,
            metadata={"ticket_id": ticket_id} if ticket_id else {},
        )
        return [{"handle": None, "role_id": None, "message_id": msg_id}]

    for h in handles:
        target_role = await get_role_by_handle(conn, h)
        if not target_role:
            logger.warning(f"[MentionRelay] Handle {h} tidak ditemukan di database.")
            continue

        target_role_id = target_role["id"]
        msg_id = await insert_message(
            conn=conn,
            project_id=project_id,
            stream_category="EXECUTION_HANDOFFS",
            event_type="THOUGHT",
            content=raw_content,
            sender_role_id=sender_id,
            scoped_recipient_role_id=target_role_id,
            metadata={"ticket_id": ticket_id, "handle": h} if ticket_id else {"handle": h},
        )
        logger.info(f"[MentionRelay] Sukses mengarahkan instruksi ke {h} ({target_role_id}) via msg [{msg_id}].")
        dispatched.append({
            "handle": h,
            "role_id": target_role_id,
            "message_id": msg_id,
        })

    return dispatched
