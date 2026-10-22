"""
Aggregator DDL Seluruh Keluarga Skema Basis Data Sovereign OS.
Menyusun 28 tabel & virtual table dalam urutan dependensi yang deterministik.
"""

from typing import List
from app.db.schemas.schema_state import STATE_DDL_LIST
from app.db.schemas.schema_organization import ORGANIZATION_DDL_LIST
from app.db.schemas.schema_workboard import WORKBOARD_DDL_LIST
from app.db.schemas.schema_memory import MEMORY_DDL_LIST
from app.db.schemas.schema_telemetry import TELEMETRY_DDL_LIST

# Urutan deterministik: State -> Org -> Workboard -> Memory -> Telemetry
ALL_DDL_STATEMENTS: List[str] = (
    STATE_DDL_LIST
    + ORGANIZATION_DDL_LIST
    + WORKBOARD_DDL_LIST
    + MEMORY_DDL_LIST
    + TELEMETRY_DDL_LIST
)


async def execute_ddl_migrations(conn) -> int:
    """Mengeksekusi seluruh pernyataan DDL secara berurutan dan idempoten."""
    executed_count = 0
    for stmt in ALL_DDL_STATEMENTS:
        clean_stmt = stmt.strip()
        if clean_stmt:
            await conn.execute(clean_stmt)
            executed_count += 1
    await conn.commit()
    return executed_count
