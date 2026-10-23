"""
War Room Moderator Subsystem.
Mengorkestrasi sesi All-Hands Executive War Room yang dimoderasi oleh CoS dan CTO.
Alur bicara diatur deterministik (Founder -> CTO -> CFO/PM -> Sintesis CoS).
"""

from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.logger import logger
from app.engine.orchestrator.event_bus import corporate_event_bus


class WarRoomModerator:
    """Moderator sesi All-Hands Executive War Room di Global Oasis (/office)."""

    async def start_war_room_session(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        founder_problem: str,
        participants: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Menjalankan sesi diskusi terarah 4-langkah dan menyiarkan hasil ke stream WAR_ROOM."""
        logger.info(f"[WarRoom] Membuka sesi All-Hands War Room untuk proyek [{project_id}]")
        actual_participants = participants or ["@cos", "@cto", "@cfo", "@pm"]

        turns: List[Dict[str, Any]] = [
            {
                "step": 1,
                "speaker": "Founder",
                "statement": f"Eskalasi Masalah: {founder_problem}",
            },
            {
                "step": 2,
                "speaker": "@cto",
                "statement": f"Evaluasi Teknis & Akar Masalah: Investigasi terhadap '{founder_problem}' mendeteksi hambatan pada layer integrasi. Mengusulkan fallback dan mitigasi latensi.",
            },
            {
                "step": 3,
                "speaker": "@cfo_pm",
                "statement": "Analisis Risiko & Dampak: Dampak operasional dapat dikendalikan dengan batas alokasi anggaran darurat.",
            },
            {
                "step": 4,
                "speaker": "@cos",
                "statement": "Sintesis Eksekutif: Kesepakatan dicapai. Arahan teknis CTO disetujui, tiket perbaikan segera diterbitkan ke Kanban Board.",
            },
        ]

        # Siarkan setiap turn ke event bus kategori WAR_ROOM
        for t in turns:
            await corporate_event_bus.publish(
                conn=conn,
                project_id=project_id,
                stream_category="WAR_ROOM",
                event_type="WAR_ROOM_MODERATION",
                content=f"[{t['speaker']}] {t['statement']}",
                sender_role_id=t["speaker"].lower().replace("@", "role_"),
                metadata={
                    "step": t["step"],
                    "participants": actual_participants,
                    "founder_problem": founder_problem,
                },
            )

        logger.info(f"[WarRoom] Sesi War Room selesai dengan 4 putaran terarah.")
        return turns


war_room_moderator = WarRoomModerator()
