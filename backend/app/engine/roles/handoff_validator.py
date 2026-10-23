"""
NEXUS Handoff Validator Subsystem.
Memvalidasi skema serah-terima kerja antar-agen otonom sesuai catalog/coordination/handoff-templates.md.
Mencegah context loss dan degradasi informasi pada koordinasi Swarm multi-agen.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.core.logger import logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StandardHandoffSchema(BaseModel):
    """Skema kontrak baku perpindahan tugas antar-agen."""
    from_role: str = Field(..., min_length=2, description="Handle peran pengirim, misal: @architect")
    to_role: str = Field(..., min_length=2, description="Handle peran penerima, misal: @frontend_developer")
    project_id: str = Field(..., min_length=1, description="ID proyek terkait")
    task_id: str = Field(..., min_length=1, description="ID tiket/tugas backlog")
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    current_state: str = Field(..., min_length=3, description="Rangkuman progress yang telah dicapai")
    deliverable: str = Field(..., min_length=3, description="Deskripsi hasil yang diminta secara spesifik")
    acceptance_criteria: List[str] = Field(..., min_length=1, description="Daftar kriteria keberhasilan yang terukur")
    relevant_files: List[str] = Field(default_factory=list, description="Daftar path file terkait")
    dependencies: List[str] = Field(default_factory=list, description="Ketergantungan tugas lain")
    quality_expectations: Optional[str] = None
    timestamp: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalisasi priority menjadi uppercase jika berupa string
            if "priority" in data and isinstance(data["priority"], str):
                data["priority"] = data["priority"].upper()
            if not data.get("timestamp"):
                data["timestamp"] = _now_iso()
        return data


class QAFeedbackSchema(BaseModel):
    """Skema umpan balik pengujian mutu (QA Verdict) PASS / FAIL."""
    task_id: str = Field(..., min_length=1)
    developer_role: str = Field(..., min_length=2)
    qa_role: str = Field(..., min_length=2)
    verdict: Literal["PASS", "FAIL"]
    attempt: int = Field(default=1, ge=1, le=3, description="Percobaan 1 hingga 3")
    evidence: List[str] = Field(default_factory=list, description="Bukti logs atau tangkapan layar")
    issues: List[Any] = Field(default_factory=list, description="Rincian kendala/kegagalan")
    notes: Optional[str] = None
    timestamp: Optional[str] = None

    @model_validator(mode="after")
    def check_issues_on_fail(self) -> "QAFeedbackSchema":
        if self.verdict == "FAIL" and not self.issues:
            raise ValueError("QA Feedback dengan verdict FAIL wajib menyertakan minimal 1 issue rincian kegagalan.")
        if not self.timestamp:
            self.timestamp = _now_iso()
        return self


class HandoffValidationResult(BaseModel):
    """Hasil evaluasi validasi skema serah-terima."""
    is_valid: bool
    handoff_type: str
    errors: List[str] = Field(default_factory=list)
    sanitized_payload: Optional[Dict[str, Any]] = None


class HandoffValidator:
    """Validator kontrak serah terima kerja antar-agen otonom."""

    def validate_standard_handoff(self, payload: Dict[str, Any]) -> HandoffValidationResult:
        """Memvalidasi payload handoff standar."""
        try:
            validated = StandardHandoffSchema(**payload)
            return HandoffValidationResult(
                is_valid=True,
                handoff_type="STANDARD",
                errors=[],
                sanitized_payload=validated.model_dump(),
            )
        except ValidationError as err:
            error_msgs = [f"{e['loc']}: {e['msg']}" for e in err.errors()]
            logger.warning(f"[HandoffValidator] Validasi standard handoff gagal: {error_msgs}")
            return HandoffValidationResult(
                is_valid=False,
                handoff_type="STANDARD",
                errors=error_msgs,
                sanitized_payload=None,
            )

    def validate_qa_feedback(self, payload: Dict[str, Any]) -> HandoffValidationResult:
        """Memvalidasi payload umpan balik QA PASS/FAIL."""
        try:
            validated = QAFeedbackSchema(**payload)
            return HandoffValidationResult(
                is_valid=True,
                handoff_type="QA_FEEDBACK",
                errors=[],
                sanitized_payload=validated.model_dump(),
            )
        except ValidationError as err:
            error_msgs = [f"{e['loc']}: {e['msg']}" for e in err.errors()]
            logger.warning(f"[HandoffValidator] Validasi QA feedback gagal: {error_msgs}")
            return HandoffValidationResult(
                is_valid=False,
                handoff_type="QA_FEEDBACK",
                errors=error_msgs,
                sanitized_payload=None,
            )

    def validate_handoff_payload(self, handoff_type: str, payload: Dict[str, Any]) -> HandoffValidationResult:
        """Dispatcher umum untuk memvalidasi berdasarkan kategori handoff."""
        upper_type = handoff_type.upper()
        if upper_type == "STANDARD":
            return self.validate_standard_handoff(payload)
        elif upper_type in ("QA", "QA_FEEDBACK", "QA_VERDICT"):
            return self.validate_qa_feedback(payload)
        else:
            return HandoffValidationResult(
                is_valid=False,
                handoff_type=upper_type,
                errors=[f"Tipe handoff '{handoff_type}' tidak dikenal."],
                sanitized_payload=None,
            )

    def format_handoff_markdown(self, handoff_type: str, payload: Dict[str, Any]) -> str:
        """Memformat payload yang tervalidasi ke format Markdown NEXUS Handoff Templates."""
        upper_type = handoff_type.upper()
        ts = payload.get("timestamp", _now_iso())

        if upper_type == "STANDARD":
            criteria_str = "\n".join([f"- [ ] {c}" for c in payload.get("acceptance_criteria", [])])
            files_str = "\n".join([f"- {f}" for f in payload.get("relevant_files", [])]) or "- (None)"
            return (
                f"# NEXUS Handoff Document\n\n"
                f"## Metadata\n"
                f"| Field | Value |\n"
                f"|---|---|\n"
                f"| **From** | {payload.get('from_role')} |\n"
                f"| **To** | {payload.get('to_role')} |\n"
                f"| **Task Reference** | {payload.get('task_id')} |\n"
                f"| **Priority** | {payload.get('priority', 'MEDIUM')} |\n"
                f"| **Timestamp** | {ts} |\n\n"
                f"## Context\n"
                f"**Project**: {payload.get('project_id')}\n"
                f"**Current State**: {payload.get('current_state')}\n"
                f"**Relevant Files**:\n{files_str}\n\n"
                f"## Deliverable Request\n"
                f"**What is needed**: {payload.get('deliverable')}\n"
                f"**Acceptance criteria**:\n{criteria_str}\n\n"
                f"## Quality Expectations\n"
                f"{payload.get('quality_expectations', 'Standard corporate quality')}\n"
            )

        elif upper_type in ("QA", "QA_FEEDBACK", "QA_VERDICT"):
            verdict = payload.get("verdict", "PASS")
            icon = "✅" if verdict == "PASS" else "❌"
            return (
                f"# NEXUS QA Verdict: {verdict} {icon}\n\n"
                f"## Task\n"
                f"| Field | Value |\n"
                f"|---|---|\n"
                f"| **Task ID** | {payload.get('task_id')} |\n"
                f"| **Developer Agent** | {payload.get('developer_role')} |\n"
                f"| **QA Agent** | {payload.get('qa_role')} |\n"
                f"| **Attempt** | {payload.get('attempt', 1)} of 3 |\n"
                f"| **Timestamp** | {ts} |\n\n"
                f"## Verdict: {verdict}\n"
                f"**Notes**: {payload.get('notes', 'None')}\n"
            )

        return f"# Handoff [{upper_type}]\nPayload: {payload}"


handoff_validator = HandoffValidator()
