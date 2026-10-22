"""
Phase 2: Turn Request & Context Assembly.
Menegakkan Invarian Suci 2 & 3:
- Scoped @mention Isolation: Hanya mengambil pesan publik atau pesan spesifik untuk peran ini.
- Byte-Stable Prompt Caching: Memisahkan Upper Static Prefix dengan Lower Volatile Context.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
import aiosqlite

from app.core.logger import logger
from app.db.repos.role_repo import get_role_by_id
from app.db.repos.tool_repo import get_sorted_tools_for_role
from app.db.repos.message_repo import list_scoped_messages_for_turn
from app.gateway.cache_boundary import assemble_cached_system_prompt


async def assemble_turn_request(
    conn: aiosqlite.Connection,
    project_id: str,
    ticket: Dict[str, Any],
    role_id: str,
) -> Tuple[str, str, str, str, List[Dict[str, Any]], str, str, List[str]]:
    """Menyusun payload permintaan turn lengkap.
    
    Mengembalikan:
        Tuple (assembled_system_prompt, user_turn_prompt, sys_digest, tool_digest, sorted_tools, model_provider, model_name, fallback_models)
    """
    # 1. Ambil definisi peran lengkap
    role = await get_role_by_id(conn, role_id)
    if not role:
        raise ValueError(f"Peran agen dengan ID {role_id} tidak ditemukan di database.")

    persona_prompt = role.get("persona_prompt", "")
    sop_template = role.get("system_prompt_template", "")
    allowed_tools_raw = role.get("tool_permissions_json", "[]")
    
    if isinstance(allowed_tools_raw, str):
        try:
            allowed_tool_ids = json.loads(allowed_tools_raw)
        except Exception:
            allowed_tool_ids = []
    else:
        allowed_tool_ids = allowed_tools_raw or []

    # 2. Ambil skema perkakas terurut secara alfabetis dari database
    sorted_tools, tool_digest = await get_sorted_tools_for_role(conn, allowed_tool_ids)

    # 3. Ambil pesan scoped @mention terisolasi untuk peran ini (Layer 3)
    scoped_msgs = await list_scoped_messages_for_turn(conn, project_id, role_id, limit=10)
    msg_lines = []
    for m in scoped_msgs:
        sender = m.get("sender_role_id") or "system"
        cat = m.get("stream_category")
        msg_lines.append(f"[{cat}] {sender}: {m.get('content', '')}")
    mentions_context = "\n".join(msg_lines) if msg_lines else "Tidak ada pesan terarah baru."

    # 4. Susun Layer 3 Dynamic Context
    blackboard_raw = ticket.get("blackboard_json", "[]")
    dynamic_context = (
        f"PROYEK ID: {project_id}\n"
        f"TIKET AKTIF: {ticket.get('id')} - {ticket.get('title')}\n"
        f"KRITERIA PENERIMAAN: {ticket.get('acceptance_criteria', '-')}\n"
        f"SHARED BLACKBOARD:\n{blackboard_raw}\n\n"
        f"SCOPED INSTRUCTIONS (@MENTION FEED):\n{mentions_context}\n"
    )

    # 5. Ekstraksi konfigurasi model peran dari basis data
    model_provider = role.get("model_provider", "anthropic")
    model_name = role.get("model_name", "claude-3-7-sonnet")
    fallbacks_raw = role.get("fallback_models_json", "[]")
    if isinstance(fallbacks_raw, str):
        try:
            fallback_models = json.loads(fallbacks_raw)
        except Exception:
            fallback_models = []
    else:
        fallback_models = fallbacks_raw or []

    # 6. Gabungkan dengan Cache Boundary
    system_prompt, sys_digest, _ = assemble_cached_system_prompt(
        persona_prompt=persona_prompt,
        sop_template=sop_template,
        sorted_tools=sorted_tools,
        dynamic_context=dynamic_context,
    )

    # 7. Susun prompt giliran pengguna
    user_prompt = (
        f"Silakan kerjakan tugas berikut:\n"
        f"Judul: {ticket.get('title')}\n"
        f"Deskripsi:\n{ticket.get('description')}\n\n"
        f"Lakukan pemikiran analisis (reasoning), dan panggil perkakas yang sesuai jika diperlukan "
        f"dalam format JSON: {{\"tool\": \"<tool_id>\", \"parameters\": {{...}}}}"
    )

    return system_prompt, user_prompt, sys_digest, tool_digest, sorted_tools, model_provider, model_name, fallback_models
