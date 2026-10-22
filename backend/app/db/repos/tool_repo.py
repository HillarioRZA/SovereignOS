"""
Repository Registri Perkakas RBAC (tool_permissions_registry).
Mengelola registri izin perkakas dan pengurutan alfabetis untuk stabilitas Prompt Cache.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple
import aiosqlite


async def register_tool_permission(
    conn: aiosqlite.Connection,
    tool_id: str,
    namespace: str,
    display_name: str,
    description: str,
    parameters_json_schema: Dict[str, Any],
    risk_tier: int = 1,
    requires_human_approval: int = 0,
) -> None:
    """Mendaftarkan atau memperbarui perkakas ke tool_permissions_registry."""
    schema_str = json.dumps(parameters_json_schema, sort_keys=True)
    await conn.execute(
        """
        INSERT INTO tool_permissions_registry (
            tool_id, namespace, display_name, description, parameters_json_schema,
            risk_tier, requires_human_approval, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(tool_id) DO UPDATE SET
            namespace = excluded.namespace,
            display_name = excluded.display_name,
            description = excluded.description,
            parameters_json_schema = excluded.parameters_json_schema,
            risk_tier = excluded.risk_tier,
            requires_human_approval = excluded.requires_human_approval,
            is_active = excluded.is_active;
        """,
        (tool_id, namespace, display_name, description, schema_str, risk_tier, requires_human_approval),
    )
    await conn.commit()


async def get_tool_permission(conn: aiosqlite.Connection, tool_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil izin perkakas terdaftar."""
    cur = await conn.execute(
        "SELECT * FROM tool_permissions_registry WHERE tool_id = ? AND is_active = 1",
        (tool_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["parameters_json_schema"] = json.loads(d["parameters_json_schema"])
    except Exception:
        pass
    return d


async def get_sorted_tools_for_role(
    conn: aiosqlite.Connection, allowed_tool_ids: List[str]
) -> Tuple[List[Dict[str, Any]], str]:
    """Mengambil skema perkakas berizin yang diurutkan secara alfabetis berdasarkan nama (sortPromptCacheToolsByName).
    
    Mengembalikan:
        Tuple (list_tools_terurut, tool_schema_digest_sha256).
    """
    if not allowed_tool_ids:
        return [], "empty_tools"

    placeholders = ",".join(["?"] * len(allowed_tool_ids))
    query = f"""
    SELECT tool_id, namespace, display_name, description, parameters_json_schema, risk_tier
    FROM tool_permissions_registry
    WHERE tool_id IN ({placeholders}) AND is_active = 1
    ORDER BY tool_id ASC;
    """
    cur = await conn.execute(query, allowed_tool_ids)
    rows = await cur.fetchall()

    sorted_tools = []
    hasher = hashlib.sha256()

    for r in rows:
        t = dict(r)
        parsed_schema = json.loads(t["parameters_json_schema"]) if isinstance(t["parameters_json_schema"], str) else t["parameters_json_schema"]
        tool_dict = {
            "name": t["tool_id"],
            "description": t["description"],
            "parameters": parsed_schema,
            "risk_tier": t["risk_tier"],
        }
        sorted_tools.append(tool_dict)
        hasher.update(f"{t['tool_id']}:{json.dumps(parsed_schema, sort_keys=True)}".encode("utf-8"))

    digest = hasher.hexdigest()
    return sorted_tools, digest
