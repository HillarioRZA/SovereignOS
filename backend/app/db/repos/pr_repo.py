"""
Repository Pull Request & Review Antar-Karyawan AI (corporate_pull_requests & corporate_pr_reviews).
Menyediakan operasi pencatatan diff kode, hasil diagnostik, dan penelaahan peer review.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import uuid
import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PRRepository:
    """Repositori asinkron untuk entitas Pull Request dan Peer Reviews."""

    async def create_pr(
        self,
        conn: aiosqlite.Connection,
        pr_id: str,
        project_id: str,
        ticket_id: str,
        author_role_id: str,
        diff_content: str,
        lsp_diagnostics: Optional[List[Dict[str, Any]]] = None,
        owasp_findings: Optional[List[Dict[str, Any]]] = None,
        status: str = "OPEN",
    ) -> Dict[str, Any]:
        """Mendaftarkan Pull Request baru ke basis data."""
        now_str = _now_iso()
        lsp_json = json.dumps(lsp_diagnostics or [])
        owasp_json = json.dumps(owasp_findings or [])

        query = """
        INSERT INTO corporate_pull_requests (
            id, project_id, ticket_id, author_role_id, diff_content,
            lsp_diagnostics_json, owasp_findings_json, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *;
        """
        cur = await conn.execute(
            query,
            (
                pr_id,
                project_id,
                ticket_id,
                author_role_id,
                diff_content,
                lsp_json,
                owasp_json,
                status,
                now_str,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()
        return dict(row) if row else {}

    async def get_pr(self, conn: aiosqlite.Connection, pr_id: str) -> Optional[Dict[str, Any]]:
        """Mengambil data Pull Request berdasarkan ID."""
        cur = await conn.execute("SELECT * FROM corporate_pull_requests WHERE id = ?", (pr_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_pr_status(
        self, conn: aiosqlite.Connection, pr_id: str, status: str
    ) -> bool:
        """Memperbarui status Pull Request (OPEN, APPROVED, CHANGES_REQUESTED, MERGED)."""
        cur = await conn.execute(
            "UPDATE corporate_pull_requests SET status = ? WHERE id = ?",
            (status, pr_id),
        )
        await conn.commit()
        return cur.rowcount > 0

    async def add_review(
        self,
        conn: aiosqlite.Connection,
        pr_id: str,
        reviewer_role_id: str,
        verdict: str,
        security_score: int = 100,
        comments: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Mencatat hasil review dari rekanan AI ke tabel corporate_pr_reviews."""
        review_id = f"rev_{uuid.uuid4().hex[:10]}"
        now_str = _now_iso()
        comments_json = json.dumps(comments or [])

        query = """
        INSERT INTO corporate_pr_reviews (
            id, pr_id, reviewer_role_id, verdict, security_score,
            comments_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING *;
        """
        cur = await conn.execute(
            query,
            (
                review_id,
                pr_id,
                reviewer_role_id,
                verdict,
                security_score,
                comments_json,
                now_str,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()
        return dict(row) if row else {}

    async def get_reviews_for_pr(
        self, conn: aiosqlite.Connection, pr_id: str
    ) -> List[Dict[str, Any]]:
        """Mengambil seluruh ulasan penelaahan untuk PR tertentu."""
        cur = await conn.execute(
            "SELECT * FROM corporate_pr_reviews WHERE pr_id = ? ORDER BY created_at ASC",
            (pr_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


pr_repo = PRRepository()
