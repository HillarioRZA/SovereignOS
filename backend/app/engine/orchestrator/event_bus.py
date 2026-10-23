"""
Corporate Asynchronous Event Bus.
Mengelola publikasi dan langganan event inter-agent secara real-time berbasis asyncio.Queue
serta persistensi log pesan ke tabel SQLite WAL (corporate_messages).
Mendukung 4 Kategori Live Stream Terfilter di Global Oasis (/office):
- ALL (semua pesan)
- EXECUTION_HANDOFFS
- CEO_DECISION_GATES
- OASIS_LOUNGE
"""

import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple
import aiosqlite

from app.core.logger import logger
from app.db.repos.message_repo import insert_message


class CorporateEventBus:
    """Event bus asinkron terdistribusi untuk komunikasi dan koordinasi antar-agen korporat."""

    VALID_STREAMS = {
        "ALL",
        "EXECUTION_HANDOFFS",
        "CEO_DECISION_GATES",
        "OASIS_LOUNGE",
        "WAR_ROOM",
        "GENERAL_THOUGHT",
    }

    def __init__(self) -> None:
        # Map: project_id -> Set of (queue, filter_category_or_none)
        self._subscribers: Dict[str, Set[Tuple[asyncio.Queue[Dict[str, Any]], Optional[str]]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, project_id: str, category: Optional[str] = None
    ) -> asyncio.Queue[Dict[str, Any]]:
        """Mendaftarkan subscriber baru untuk proyek tertentu dengan opsi filter stream category."""
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            if project_id not in self._subscribers:
                self._subscribers[project_id] = set()
            self._subscribers[project_id].add((queue, category))
            logger.debug(f"[EventBus] Subscribed: Project [{project_id}], Category [{category}]")
        return queue

    async def unsubscribe(self, project_id: str, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        """Melepas pendaftaran antrean subscriber dari registry proyek."""
        async with self._lock:
            if project_id in self._subscribers:
                to_remove = {item for item in self._subscribers[project_id] if item[0] is queue}
                self._subscribers[project_id] -= to_remove
                if not self._subscribers[project_id]:
                    del self._subscribers[project_id]
                logger.debug(f"[EventBus] Unsubscribed: Project [{project_id}]")

    async def publish(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        stream_category: str,
        event_type: str,
        content: str,
        sender_role_id: Optional[str] = None,
        scoped_recipient_role_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Menyimpan pesan ke database corporate_messages dan menyiarkannya in-memory (0-token idle)."""
        cat = stream_category if stream_category in self.VALID_STREAMS else "GENERAL_THOUGHT"
        msg_id = await insert_message(
            conn=conn,
            project_id=project_id,
            stream_category=cat,
            event_type=event_type,
            content=content,
            sender_role_id=sender_role_id,
            scoped_recipient_role_id=scoped_recipient_role_id,
            metadata=metadata or {},
        )

        payload: Dict[str, Any] = {
            "id": msg_id,
            "project_id": project_id,
            "stream_category": cat,
            "event_type": event_type,
            "content": content,
            "sender_role_id": sender_role_id,
            "scoped_recipient_role_id": scoped_recipient_role_id,
            "metadata": metadata or {},
        }

        # Broadcast ke seluruh subscriber proyek yang cocok dengan filter kategorinya
        async with self._lock:
            subs = list(self._subscribers.get(project_id, set()))
            # Global subscribers ('*') jika ada
            subs.extend(self._subscribers.get("*", set()))

        for sub_queue, sub_cat in subs:
            # Jika sub_cat None atau 'ALL', terima semua. Kalau ditentukan, hanya jika cocok
            if sub_cat is None or sub_cat == "ALL" or sub_cat == cat:
                try:
                    sub_queue.put_nowait(payload)
                except asyncio.QueueFull:
                    logger.warning(f"[EventBus] Queue full for subscriber in project [{project_id}].")

        logger.info(f"[EventBus] Broadcast [{cat}:{event_type}] from {sender_role_id} in {project_id}")
        return payload


corporate_event_bus = CorporateEventBus()
