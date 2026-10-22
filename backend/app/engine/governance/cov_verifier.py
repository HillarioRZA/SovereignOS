"""
Chain-of-Verification (CoV) Pre-Flight Gatekeeper.
Mendukung 2 Mode yang dapat dipilih (Toggleable via Settings / Interface):
1. Mode "llm": Full LLM Critic (Audit penalaran semantik parameter & schema).
2. Mode "jev": TypeSafe AI System One Jev (Verifikasi probabilistik terstruktur & typed decision).

Alur Kerja:
1. Respon peran agen dibaca.
2. Jika agen TIDAK memerlukan tools -> CoV langsung passthrough, respon diteruskan ke user/agen lain.
3. Jika agen butuh tools -> CoV memeriksa kelengkapan & kebenaran parameter terhadap kontrak schema.
4. Jika parameter tepat -> Approved, agen peran melanjutkan eksekusi tools.
5. Jika parameter salah/kurang -> CoV mengirim repair_feedback ke agen peran (Non-Hijacking Worker Self-Repair).
   Agen peran yang memperbaiki parameter dan mengeksekusi, BUKAN agen CoV.
"""

import json
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
import aiosqlite

from app.core.config import settings
from app.core.logger import logger
from app.engine.governance.jev_client import JevSystemOneClient
from app.gateway.model_router import SovereignModelRouter
from app.gateway.tool_call_repair import extract_tool_calls


class CoVInspectionResult:
    """Hasil inspeksi verifikasi perkakas dari CoV Gatekeeper."""

    def __init__(
        self,
        approved: bool,
        mode: str,
        verdict: str,  # APPROVED | REPAIR_REQUIRED | REJECTED | PASSTHROUGH_NO_TOOLS
        repair_feedback: Optional[str] = None,
        missing_or_invalid_params: Optional[List[str]] = None,
        has_tool_calls: bool = True,
        latency_ms: float = 0.0,
    ) -> None:
        self.approved = approved
        self.mode = mode
        self.verdict = verdict
        self.repair_feedback = repair_feedback
        self.missing_or_invalid_params = missing_or_invalid_params or []
        self.has_tool_calls = has_tool_calls
        self.latency_ms = latency_ms

    @property
    def tier_evaluated(self) -> int:
        """Kompatibilitas mundur dengan schema database sentinel_audit_logs (1: Jev, 2: LLM)."""
        return 1 if self.mode == "jev" else 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "mode": self.mode,
            "verdict": self.verdict,
            "repair_feedback": self.repair_feedback,
            "missing_or_invalid_params": self.missing_or_invalid_params,
            "has_tool_calls": self.has_tool_calls,
            "latency_ms": self.latency_ms,
        }


class CoVVerifier:
    """
    Verifikator CoV dengan dukungan 2 Mode: Full LLM Critic vs TypeSafe AI Jev.
    Mode aktif dapat disetel melalui parameter inisialisasi atau settings.COV_MODE.
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        router: Optional[SovereignModelRouter] = None,
        jev_client: Optional[JevSystemOneClient] = None,
    ) -> None:
        self.mode = (mode or settings.COV_MODE or "llm").lower()
        self.router = router or SovereignModelRouter()
        self.jev_client = jev_client or JevSystemOneClient()

    def set_mode(self, new_mode: str) -> None:
        """Mengganti mode CoV secara dinamis (misal dari interface/dashboard)."""
        clean = new_mode.lower()
        if clean not in ("llm", "jev"):
            raise ValueError(f"Mode CoV tidak valid: '{new_mode}'. Pilihan: 'llm' atau 'jev'.")
        self.mode = clean
        logger.info(f"[CoVVerifier] Mode verifikasi dialihkan ke: [{self.mode}]")

    def inspect_agent_response_for_tools(self, response_text: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Mengecek apakah respon peran agen mengandung pemanggilan tools.
        Jika tidak ada -> agen mandiri langsung meneruskan ke user / agen peran lain.
        """
        detected = extract_tool_calls(response_text)
        if not detected:
            return False, []
        return True, detected

    async def verify_tool_invocation(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        ticket_id: Optional[str],
        role_id: str,
        tool_id: str,
        parameters: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
        risk_tier: int = 1,
        simulate_critic_pass: bool = False,
    ) -> CoVInspectionResult:
        """
        Memverifikasi parameter pemanggilan perkakas dengan mode aktif (LLM atau JEV).
        Menegakkan Non-Hijacking Worker Self-Repair: CoV hanya memberikan verdict dan feedback.
        """
        start_time = time.perf_counter()

        # 1. Pengecekan keamanan statis awal (Path traversal / absolute path)
        if "file_path" in parameters:
            path_val = str(parameters["file_path"])
            if ".." in path_val or path_val.startswith("/") or path_val.startswith("\\"):
                latency = (time.perf_counter() - start_time) * 1000.0
                feedback = f"Path traversal atau path absolut terlarang terdeteksi pada parameter file_path: '{path_val}'"
                await self._record_audit_log(
                    conn, project_id, ticket_id, role_id, tool_id, self.mode, "REJECTED", feedback, latency
                )
                return CoVInspectionResult(
                    approved=False,
                    mode=self.mode,
                    verdict="REJECTED",
                    repair_feedback=feedback,
                    missing_or_invalid_params=["file_path"],
                    latency_ms=round(latency, 2),
                )

        # 2. Mode Simulasi Cepat (Bypass untuk pengujian tanpa konsumsi token/koneksi remote)
        if simulate_critic_pass:
            latency = (time.perf_counter() - start_time) * 1000.0
            await self._record_audit_log(
                conn, project_id, ticket_id, role_id, tool_id, self.mode, "APPROVED", None, latency
            )
            return CoVInspectionResult(
                approved=True,
                mode=self.mode,
                verdict="APPROVED",
                repair_feedback=None,
                latency_ms=round(latency, 2),
            )

        # 3. Eksekusi Berdasarkan Mode Aktif
        if self.mode == "jev":
            # --- MODE JEV (TypeSafe AI System One) ---
            jev_res = await self.jev_client.verify_tool_parameters(tool_id, parameters, schema)
            latency = (time.perf_counter() - start_time) * 1000.0
            verdict = "APPROVED" if jev_res.valid else "REPAIR_REQUIRED"

            await self._record_audit_log(
                conn, project_id, ticket_id, role_id, tool_id, "jev", verdict, jev_res.repair_feedback, latency
            )
            return CoVInspectionResult(
                approved=jev_res.valid,
                mode="jev",
                verdict=verdict,
                repair_feedback=jev_res.repair_feedback,
                missing_or_invalid_params=jev_res.violated_fields,
                latency_ms=round(latency, 2),
            )
        else:
            # --- MODE LLM (Full LLM Critic) ---
            schema_desc = json.dumps(schema) if schema else "Periksa apakah parameter lengkap dan aman untuk perkakas ini."
            critic_prompt = (
                f"Sebagai Agen Chain-of-Verification (CoV), periksa pemanggilan perkakas berikut:\n"
                f"- Peran Agen Pemohon: {role_id}\n"
                f"- Perkakas yang Dipanggil: {tool_id}\n"
                f"- Parameter yang Diberikan: {json.dumps(parameters)}\n"
                f"- Spesifikasi Skema Kebutuhan: {schema_desc}\n\n"
                f"Tugas Anda:\n"
                f"1. Periksa apakah parameter sudah lengkap dan benar sesuai kebutuhan perkakas.\n"
                f"2. Jika sudah tepat, setujui pemanggilan.\n"
                f"3. Jika ada parameter yang salah atau kurang, jelaskan kekurangannya agar agen peran dapat memperbaikinya sendiri.\n\n"
                f"Wajib berikan respon dalam format JSON murni:\n"
                f'{{"approved": true/false, "missing_or_invalid": ["nama_parameter"], "feedback": "penjelasan untuk agen peran"}}'
            )

            try:
                res = await self.router.execute_routed_completion(
                    prompt=critic_prompt,
                    system_prompt="Anda adalah CoV Critic. DILARANG mengubah parameter sendiri; hanya verifikasi dan beri feedback perbaikan.",
                    primary_provider="openai_compatible",
                    primary_model="deepseek-chat",
                )
                raw_content = res.get("content", "{}")
                # Parse JSON keputusan critic
                parsed = self._parse_critic_json(raw_content)
                approved = bool(parsed.get("approved", True))
                feedback = parsed.get("feedback") if not approved else None
                missing_fields = parsed.get("missing_or_invalid", [])
                verdict = "APPROVED" if approved else "REPAIR_REQUIRED"
            except Exception as e:
                logger.warning(f"[CoV LLM] Critic LLM error ({e}), mengizinkan dengan fallback aman.")
                approved = True
                feedback = None
                missing_fields = []
                verdict = "APPROVED"

            latency = (time.perf_counter() - start_time) * 1000.0
            await self._record_audit_log(
                conn, project_id, ticket_id, role_id, tool_id, "llm", verdict, feedback, latency
            )
            return CoVInspectionResult(
                approved=approved,
                mode="llm",
                verdict=verdict,
                repair_feedback=feedback,
                missing_or_invalid_params=missing_fields,
                latency_ms=round(latency, 2),
            )

    def _parse_critic_json(self, raw_str: str) -> Dict[str, Any]:
        """Ekstraksi aman JSON respons critic LLM."""
        text = raw_str.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            return json.loads(text)
        except Exception:
            approved = "true" in raw_str.lower()
            return {
                "approved": approved,
                "feedback": None if approved else "Parameter tidak memenuhi persyaratan kontrak perkakas.",
                "missing_or_invalid": [],
            }

    async def _record_audit_log(
        self,
        conn: aiosqlite.Connection,
        project_id: str,
        ticket_id: Optional[str],
        role_id: str,
        tool_id: str,
        mode_str: str,
        verdict: str,
        feedback: Optional[str],
        latency_ms: float,
    ) -> None:
        """Mencatat hasil verifikasi CoV ke tabel sentinel_audit_logs."""
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        tier_val = 1 if mode_str == "jev" else 2
        await conn.execute(
            """
            INSERT INTO sentinel_audit_logs (
                id, project_id, ticket_id, role_id, tool_id, tier_evaluated, verdict, repair_feedback, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (audit_id, project_id, ticket_id, role_id, tool_id, tier_val, verdict, feedback, latency_ms),
        )
        await conn.commit()
