"""
Agency Loader: Ingesti Deklaratif Katalog 130+ Agen (Zero-Code-Touch).
Mem-parsing divisions.json, runbooks.json, dan seluruh file agent .md ke basis data.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid
import yaml
import aiosqlite

from app.core.config import settings
from app.core.logger import logger
from app.db.repos.role_repo import upsert_role

# Pemetaan handle singkat kanonikal eksekutif & teknis
SHORTCUT_HANDLES = {
    "chief of staff": "@cos",
    "chief technology officer": "@cto",
    "software architect": "@cto",
    "product manager": "@pm",
    "frontend developer": "@fe",
    "frontend engineer": "@fe",
    "backend architect": "@be",
    "backend engineer": "@be",
    "qa & secops engineer": "@qa",
    "code reviewer": "@qa",
    "executive secretary": "@secretary",
    "chief financial officer": "@cfo",
}


def _split_markdown_sections(content: str) -> Tuple[Dict[str, Any], str, str]:
    """Mengekstrak YAML frontmatter, Layer 1 (Soul/Persona), dan Layer 2 (SOP)."""
    frontmatter: Dict[str, Any] = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                pass
            body = parts[2].strip()

    # Pisahkan Layer 1 (Identity/Personality) dan Layer 2 (Core Mission & Rules)
    mission_marker = re.search(r"##\s+(?:🎯\s+)?(?:Your\s+)?Core\s+Mission", body, re.IGNORECASE)
    if mission_marker:
        idx = mission_marker.start()
        persona_prompt = body[:idx].strip()
        sop_prompt = body[idx:].strip()
    else:
        # Fallback jika marker tidak ada: 40% awal = Persona, sisanya = SOP
        split_point = int(len(body) * 0.4)
        persona_prompt = body[:split_point].strip()
        sop_prompt = body[split_point:].strip()

    return frontmatter, persona_prompt, sop_prompt


def _generate_handle(name: str) -> str:
    """Menghasilkan handle @mention deterministik."""
    clean_name = name.strip().lower()
    if clean_name in SHORTCUT_HANDLES:
        return SHORTCUT_HANDLES[clean_name]
    slug = re.sub(r"[^a-z0-9]+", "-", clean_name).strip("-")
    return f"@{slug}"


async def ingest_divisions(conn: aiosqlite.Connection, catalog_path: Path) -> int:
    """Mengimpor 16+ divisi dari divisions.json ke corporate_divisions."""
    div_file = catalog_path / "divisions.json"
    if not div_file.exists():
        logger.warning(f"divisions.json tidak ditemukan di {div_file}")
        return 0

    with open(div_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    divs = data.get("divisions", {})
    count = 0
    idx = 0
    for slug, meta in divs.items():
        if isinstance(meta, dict):
            name = meta.get("label", slug.title())
            icon = meta.get("icon", "Folder")
            color = meta.get("color", "#3B82F6")
        else:
            name = str(meta).title()
            icon = "Folder"
            color = "#3B82F6"

        div_id = f"div_{slug.replace('-', '_')}"
        purpose = f"Divisi spesialisasi industri untuk {name}."

        await conn.execute(
            """
            INSERT INTO corporate_divisions (id, name, slug, purpose, accent_color, icon_name, order_index)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                slug = excluded.slug,
                purpose = excluded.purpose,
                accent_color = excluded.accent_color,
                icon_name = excluded.icon_name,
                order_index = excluded.order_index;
            """,
            (div_id, name, slug, purpose, color, icon, idx),
        )
        idx += 1
        count += 1
    await conn.commit()
    logger.info(f"{count} divisi berhasil diimpor dari divisions.json.")
    return count


async def ingest_runbooks(conn: aiosqlite.Connection, catalog_path: Path) -> int:
    """Mengimpor runbook alur kerja dari runbooks.json ke corporate_runbooks."""
    rb_file = catalog_path / "runbooks.json"
    if not rb_file.exists():
        return 0

    try:
        with open(rb_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Gagal membaca runbooks.json: {e}")
        return 0

    runbooks = data.get("runbooks", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    count = 0
    for rb in runbooks:
        rb_id = rb.get("id", f"rb_{uuid.uuid4().hex[:8]}")
        name = rb.get("name", "Standard Runbook")
        desc = rb.get("description", "")
        stages = json.dumps(rb.get("stages", rb.get("dag_stages", [])))

        await conn.execute(
            """
            INSERT INTO corporate_runbooks (id, name, description, dag_stages_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                dag_stages_json = excluded.dag_stages_json;
            """,
            (rb_id, name, desc, stages),
        )
        count += 1
    await conn.commit()
    logger.info(f"{count} runbook alur kerja berhasil diimpor.")
    return count


async def ingest_agents_catalog(
    conn: aiosqlite.Connection,
    catalog_path: Optional[Path] = None,
) -> Dict[str, int]:
    """Memindai seluruh berkas .md pada catalog/agents/ dan menyimpannya ke corporate_roles."""
    cat_dir = catalog_path or settings.CATALOG_DIR
    agents_dir = cat_dir / "agents"

    # Step 1: Ingest Divisi & Runbooks
    div_count = await ingest_divisions(conn, cat_dir)
    rb_count = await ingest_runbooks(conn, cat_dir)

    # Step 2: Ingest 130+ Agen
    agent_files = list(agents_dir.glob("**/*.md")) if agents_dir.exists() else []
    role_count = 0

    for fpath in agent_files:
        try:
            content = fpath.read_text(encoding="utf-8")
            frontmatter, persona, sop = _split_markdown_sections(content)

            role_name = frontmatter.get("name") or fpath.stem.replace("-", " ").title()
            job_desc = frontmatter.get("description") or f"Spesialis agen otonom untuk {role_name}."
            handle = _generate_handle(role_name)

            # Tentukan division_id dari folder divisi tingkat pertama di catalog/agents
            rel_parts = fpath.relative_to(agents_dir).parts
            division_slug = rel_parts[0] if rel_parts else fpath.parent.name
            div_id = f"div_{division_slug.replace('-', '_')}"

            # UUID 100% slug-free untuk id peran
            role_uuid = f"role_{uuid.uuid5(uuid.NAMESPACE_DNS, fpath.stem).hex}"

            # Alat default yang diizinkan
            allowed_tools = ["builtin:read_file", "builtin:list_directory", "builtin:search_files"]
            if any(k in fpath.stem for k in ["engineer", "architect", "developer", "builder", "optimizer"]):
                allowed_tools.extend(["builtin:write_file", "ptc:execute_code"])

            await upsert_role(
                conn=conn,
                role_id=role_uuid,
                division_id=div_id,
                handle_mention=handle,
                name=role_name,
                job_description=job_desc,
                persona_prompt=persona,
                system_prompt_template=sop,
                model_provider="anthropic",
                model_name="claude-3-7-sonnet",
                fallback_models=["openai/gpt-4o", "gemini/gemini-2.5-flash"],
                tool_permissions=allowed_tools,
            )
            role_count += 1
        except Exception as err:
            logger.error(f"Gagal mengimpor agen dari {fpath}: {err}")

    logger.info(f"Ingesti selesai: {div_count} Divisi, {rb_count} Runbooks, {role_count} Agen Peran.")
    return {"divisions": div_count, "runbooks": rb_count, "roles": role_count}
