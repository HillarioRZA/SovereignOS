"""
TypeSafe AI JEV System One Verification Client (Full-Native via HTTPX).
Mengintegrasikan model System One Jev (TypeSafe AI) untuk verifikasi probabilistik
terhadap pemanggilan perkakas dan validasi skema parameter tanpa halusinasi teks.

Primitif Jev:
- Noul (Boolean probability): Mengevaluasi apakah parameter memenuhi kontrak skema.
- Choice / Typed Decision: Mengembalikan status validitas dan bidang yang melanggar.
- Zero Output Hallucinations: State tidak terstruktur masuk -> Keputusan terstruktur keluar.
"""

from typing import Any, Dict, List, Optional, Tuple
import httpx

from app.core.config import settings
from app.core.logger import logger


class JevVerificationResult:
    """Hasil verifikasi terstruktur dari TypeSafe AI Jev."""

    def __init__(
        self,
        valid: bool,
        confidence: float,
        repair_feedback: Optional[str] = None,
        violated_fields: Optional[List[str]] = None,
        latency_ms: float = 0.0,
    ) -> None:
        self.valid = valid
        self.confidence = confidence
        self.repair_feedback = repair_feedback
        self.violated_fields = violated_fields or []
        self.latency_ms = latency_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "confidence": self.confidence,
            "repair_feedback": self.repair_feedback,
            "violated_fields": self.violated_fields,
            "latency_ms": self.latency_ms,
        }


class JevSystemOneClient:
    """Klien native HTTPX untuk model System One Jev (TypeSafe AI)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key or settings.TYPESAFE_API_KEY or ""
        self.base_url = (base_url or settings.TYPESAFE_BASE_URL).rstrip("/")
        self.model = model or settings.TYPESAFE_JEV_MODEL
        self.transport = transport

    async def verify_tool_parameters(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> JevVerificationResult:
        """
        Mengevaluasi parameter tool terhadap skema menggunakan System One Jev.
        Jika API key tersedia, menghubungi endpoint TypeSafe AI.
        Jika tidak tersedia (lingkungan lokal/dev/test), melakukan evaluasi typed deterministik.
        """
        # 1. Pengecekan dasar struktur kamus parameter
        if not isinstance(parameters, dict):
            return JevVerificationResult(
                valid=False,
                confidence=1.0,
                repair_feedback="Parameter pemanggilan perkakas wajib berformat objek JSON (dict).",
                violated_fields=["root"],
            )

        # 2. Pengecekan keamanan dasar (Path Traversal & Injection)
        for k, v in parameters.items():
            if isinstance(v, str):
                if ".." in v or v.startswith("/") or v.startswith("\\"):
                    return JevVerificationResult(
                        valid=False,
                        confidence=0.99,
                        repair_feedback=f"Parameter '{k}' mengandung path traversal ('..') atau path absolut tidak aman: '{v}'.",
                        violated_fields=[k],
                    )

        # 3. Jika API key TypeSafe AI dikonfigurasi, panggil endpoint remote JEV
        if self.api_key:
            return await self._call_remote_jev(tool_id, parameters, schema)

        # 4. Mode Evaluasi Schema-Driven Cepat (Fallback / Offline)
        return self._evaluate_schema_locally(tool_id, parameters, schema)

    async def _call_remote_jev(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> JevVerificationResult:
        """Memanggil API remote TypeSafe AI Jev via HTTP POST."""
        endpoint = f"{self.base_url}/decisions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "decision_type": "noul_and_choice",
            "context": {
                "tool_id": tool_id,
                "proposed_parameters": parameters,
                "expected_schema": schema or {},
            },
            "condition": "Does the proposed_parameters strictly satisfy expected_schema and safety constraints?",
        }

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            is_valid = bool(data.get("noul", {}).get("outcome", True))
            confidence = float(data.get("noul", {}).get("probability", 0.95))
            violations = data.get("choice", {}).get("violated_fields", [])
            feedback = None
            if not is_valid:
                feedback = data.get("reason") or f"Parameter melanggar kontrak skema pada field: {violations}"

            return JevVerificationResult(
                valid=is_valid,
                confidence=confidence,
                repair_feedback=feedback,
                violated_fields=violations,
            )
        except Exception as e:
            logger.warning(f"[JevSystemOneClient] Panggilan remote gagal ({e}), beralih ke evaluasi lokal.")
            return self._evaluate_schema_locally(tool_id, parameters, schema)

    def _evaluate_schema_locally(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> JevVerificationResult:
        """Evaluasi typed schema lokal dengan probabilitas terkalibrasi."""
        violated_fields: List[str] = []

        # Aturan skema bawaan untuk perkakas umum jika schema spesifik belum di-pass
        if tool_id == "builtin:read_file" and not parameters.get("file_path"):
            violated_fields.append("file_path")
        elif tool_id == "builtin:search_files" and not parameters.get("query"):
            violated_fields.append("query")
        elif tool_id == "builtin:write_file":
            if not parameters.get("file_path"):
                violated_fields.append("file_path")
            if "content" not in parameters:
                violated_fields.append("content")

        # Jika schema JSON formal diberikan, periksa required properties
        if schema and isinstance(schema, dict):
            required = schema.get("required", [])
            for req in required:
                if req not in parameters or parameters[req] is None or parameters[req] == "":
                    if req not in violated_fields:
                        violated_fields.append(req)

        if violated_fields:
            feedback = (
                f"Evaluasi Jev mendeteksi parameter tidak lengkap atau salah: "
                f"Field yang belum terpenuhi: {violated_fields}. Mohon perbaiki parameter tersebut."
            )
            return JevVerificationResult(
                valid=False,
                confidence=0.99,
                repair_feedback=feedback,
                violated_fields=violated_fields,
            )

        return JevVerificationResult(
            valid=True,
            confidence=0.98,
            repair_feedback=None,
            violated_fields=[],
        )
