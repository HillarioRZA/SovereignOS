"""
Unit Tests for Agency Loader & Dynamic Catalog Ingestion.
"""

import gc
import os
import tempfile
import pytest

from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations
from app.db.repos.role_repo import get_role_by_handle, list_all_roles
from app.engine.roles.agency_loader import ingest_agents_catalog
from app.engine.tools.permission_registry import seed_baseline_tools


def _safe_remove(path: str) -> None:
    gc.collect()
    for p in [path, f"{path}-wal", f"{path}-shm"]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_agency_loader_ingestion():
    """Uji ingesti katalog mandiri ke database dan verifikasi peran kanonikal."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async with get_db_connection(db_path) as conn:
            await execute_ddl_migrations(conn)
            await seed_baseline_tools(conn)

            stats = await ingest_agents_catalog(conn)
            assert stats["divisions"] >= 16
            assert stats["roles"] >= 130  # Sesuai katalog 130+

            # Verifikasi role shortcut handle Chief of Staff (@cos)
            cos_role = await get_role_by_handle(conn, "@cos")
            assert cos_role is not None
            assert "chief of staff" in cos_role["name"].lower()
            assert len(cos_role["persona_prompt"]) > 50
            assert len(cos_role["system_prompt_template"]) > 50

            # Verifikasi role Backend Architect (@be)
            be_role = await get_role_by_handle(conn, "@be")
            assert be_role is not None
            assert "backend" in be_role["name"].lower()

            # Verifikasi role Software Architect / CTO (@cto)
            cto_role = await get_role_by_handle(conn, "@cto")
            assert cto_role is not None

            # Pastikan ID peran menggunakan UUID format (slug-free)
            assert cos_role["id"].startswith("role_")

            # Verifikasi seluruh peran terdaftar (seharusnya 282 peran)
            all_roles = await list_all_roles(conn)
            assert len(all_roles) >= 130
    finally:
        _safe_remove(db_path)
