"""
Repository Pesan Korporat & Live Stream Oasis (corporate_messages).
Mendukung 4 kategori live stream, isolasi konteks @mention, dan pencarian FTS5.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import uuid
import aiosqlite


async def insert_message(
    conn: aiosqlite.Connection,
    project_id: str,
    stream_category: str,
    event_type: str,
    content: str,
    sender_role_id: Optional[str] = None,
    scoped_recipient_role_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Menyimpan pesan/event baru ke dalam corporate_messages dan indeks FTS5."""
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    meta_json = json.dumps(metadata or {})
    now_str = datetime.now(timezone.utc).isoformat()

    await conn.execute(
        """
        INSERT INTO corporate_messages (
            id, project_id, stream_category, sender_role_id, scoped_recipient_role_id,
            event_type, content, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            msg_id, project_id, stream_category, sender_role_id,
            scoped_recipient_role_id, event_type, content, meta_json, now_str
        ),
    )
    # Masukkan ke FTS5
    try:
        await conn.execute(
            "INSERT INTO messages_fts (rowid, content, project_id, sender_role_id) VALUES (last_insert_rowid(), ?, ?, ?)",
            (content, project_id, sender_role_id or ""),
        )
    except Exception:
        pass

    await conn.commit()
    return msg_id


async def list_stream_messages(
    conn: aiosqlite.Connection,
    project_id: str,
    stream_category: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Mengambil pesan untuk feed Global Oasis (/office). Jika category kosong, mengambil seluruh stream."""
    if stream_category and stream_category != "ALL":
        cur = await conn.execute(
            """
            SELECT * FROM corporate_messages
            WHERE project_id = ? AND stream_category = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (project_id, stream_category, limit),
        )
    else:
        cur = await conn.execute(
            """
            SELECT * FROM corporate_messages
            WHERE project_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (project_id, limit),
        )
    rows = await cur.fetchall()
    return [dict(r) for r in reversed(rows)]


async def list_scoped_messages_for_turn(
    conn: aiosqlite.Connection,
    project_id: str,
    current_role_id: str,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Mengambil pesan untuk perakitan Layer 3 Context.
    
    Hanya menyertakan pesan publik (scoped_recipient_role_id IS NULL)
    atau instruksi yang secara spesifik ditujukan ke peran ini (scoped_recipient_role_id = :role_id).
    Mencegah pencemaran context window agen lain secara 100%.
    """
    cur = await conn.execute(
        """
        SELECT * FROM corporate_messages
        WHERE project_id = ? 
          AND (scoped_recipient_role_id IS NULL OR scoped_recipient_role_id = ?)
        ORDER BY created_at DESC LIMIT ?
        """,
        (project_id, current_role_id, limit),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in reversed(rows)]
