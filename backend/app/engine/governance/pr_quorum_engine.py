"""
Autonomous Peer-to-Peer PR Quorum Engine.
Menegakkan gerbang mutu penjaminan kode (Quorum Approval Gate):
Kode hanya dapat disetujui jika mendapatkan minimal >= 2 persetujuan (approvals)
dari peninjau independen (QA, Security, Peer Specialist) tanpa penolakan aktif.
"""

from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.logger import logger
from app.db.repos.pr_repo import pr_repo
from app.engine.orchestrator.event_bus import corporate_event_bus


class PRQuorumEngine:
    """Mesin konsensus kuorum peer review kode otonom."""

    async def submit_review(
        self,
        conn: aiosqlite.Connection,
        pr_id: str,
        reviewer_role_id: str,
        verdict: str,
        security_score: int = 100,
        comments: Optional[List[str]] = None,
        quorum_required: int = 2,
    ) -> Dict[str, Any]:
        """Menyimpan review kode dari agen peninjau dan mengevaluasi status kuorum."""
        # 1. Simpan ulasan ke database
        rev = await pr_repo.add_review(
            conn=conn,
            pr_id=pr_id,
            reviewer_role_id=reviewer_role_id,
            verdict=verdict,
            security_score=security_score,
            comments=comments,
        )

        # 2. Ambil seluruh review aktif untuk PR ini
        all_reviews = await pr_repo.get_reviews_for_pr(conn, pr_id)
        pr = await pr_repo.get_pr(conn, pr_id)
        project_id = pr["project_id"] if pr else "unknown"

        # 3. Evaluasi kuorum
        has_rejection = any(r["verdict"] == "CHANGES_REQUESTED" or r["security_score"] < 70 for r in all_reviews)
        approvals = [r for r in all_reviews if r["verdict"] == "APPROVED" and r["security_score"] >= 70]
        approvals_count = len(approvals)

        if has_rejection:
            new_status = "CHANGES_REQUESTED"
            quorum_met = False
        elif approvals_count >= quorum_required:
            new_status = "APPROVED"
            quorum_met = True
        else:
            new_status = "OPEN"
            quorum_met = False

        # Update status di tabel corporate_pull_requests
        await pr_repo.update_pr_status(conn, pr_id, new_status)

        if quorum_met:
            await corporate_event_bus.publish(
                conn=conn,
                project_id=project_id,
                stream_category="EXECUTION_HANDOFFS",
                event_type="PR_APPROVED",
                content=f"Pull Request [{pr_id}] memenuhi kuorum ({approvals_count}/{quorum_required} approvals) -> APPROVED.",
                sender_role_id=reviewer_role_id,
                metadata={"pr_id": pr_id, "approvals_count": approvals_count},
            )
            logger.info(f"[PRQuorum] PR [{pr_id}] Kuorum terpenuhi ({approvals_count}/{quorum_required}) -> APPROVED.")
        else:
            logger.info(f"[PRQuorum] PR [{pr_id}] Status: {new_status} ({approvals_count}/{quorum_required} approvals).")

        return {
            "review_id": rev.get("id"),
            "pr_id": pr_id,
            "verdict": verdict,
            "security_score": security_score,
            "approvals_count": approvals_count,
            "quorum_required": quorum_required,
            "quorum_met": quorum_met,
            "status": new_status,
        }


pr_quorum_engine = PRQuorumEngine()
