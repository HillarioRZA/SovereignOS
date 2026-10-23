"""
Unit tests for HandoffValidator (NEXUS Handoff Templates contract verification).
Menguji validasi skema serah-terima antar-agen otonom untuk mencegah context loss.
"""

import pytest
from app.engine.roles.handoff_validator import (
    handoff_validator,
    HandoffValidator,
    HandoffValidationResult,
)


def test_validate_standard_handoff_success():
    payload = {
        "from_role": "@architect",
        "to_role": "@frontend_developer",
        "project_id": "proj_omega",
        "task_id": "task_101",
        "priority": "HIGH",
        "current_state": "Architecture design completed and approved by Founder.",
        "deliverable": "Build responsive navigation bar and dashboard shell.",
        "acceptance_criteria": [
            "Must be responsive on mobile and desktop",
            "Must pass accessibility audit with 0 violations",
        ],
        "relevant_files": ["frontend/components/Navbar.tsx", "frontend/styles/theme.css"],
        "quality_expectations": "100% TypeScript type safety, 0 lint errors.",
    }

    result = handoff_validator.validate_standard_handoff(payload)
    assert result.is_valid is True
    assert result.handoff_type == "STANDARD"
    assert len(result.errors) == 0
    assert result.sanitized_payload is not None
    assert result.sanitized_payload["priority"] == "HIGH"


def test_validate_standard_handoff_missing_required_fields():
    # Rumpang: tanpa acceptance_criteria dan deliverable kosong
    incomplete_payload = {
        "from_role": "@architect",
        "to_role": "@frontend_developer",
        "project_id": "proj_omega",
        "task_id": "task_101",
        "priority": "INVALID_PRIORITY",
        "current_state": "",
        "deliverable": "",
        "acceptance_criteria": [],
    }

    result = handoff_validator.validate_standard_handoff(incomplete_payload)
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert any("acceptance_criteria" in err for err in result.errors)


def test_validate_qa_feedback_pass_and_fail_modes():
    # QA PASS
    pass_payload = {
        "task_id": "task_101",
        "developer_role": "@frontend_developer",
        "qa_role": "@qa_engineer",
        "verdict": "PASS",
        "attempt": 1,
        "evidence": ["test_run.log", "screenshot_desktop.png"],
        "notes": "Verified responsive layout and clean accessibility tree.",
    }
    result_pass = handoff_validator.validate_qa_feedback(pass_payload)
    assert result_pass.is_valid is True
    assert result_pass.handoff_type == "QA_FEEDBACK"

    # QA FAIL tanpa rincian issues (wajib ada issues jika verdict == FAIL)
    fail_payload_without_issues = {
        "task_id": "task_101",
        "developer_role": "@frontend_developer",
        "qa_role": "@qa_engineer",
        "verdict": "FAIL",
        "attempt": 2,
        "issues": [],  # Harus diisi jika gagal
    }
    result_fail = handoff_validator.validate_qa_feedback(fail_payload_without_issues)
    assert result_fail.is_valid is False
    assert any("issue" in err.lower() for err in result_fail.errors)


def test_format_handoff_markdown():
    payload = {
        "from_role": "@architect",
        "to_role": "@fe",
        "project_id": "proj_demo",
        "task_id": "ticket_77",
        "priority": "CRITICAL",
        "current_state": "Discovery done.",
        "deliverable": "Core MVP page.",
        "acceptance_criteria": ["Lighthouse > 90"],
    }
    md_output = handoff_validator.format_handoff_markdown("STANDARD", payload)
    assert "# NEXUS Handoff Document" in md_output
    assert "@architect" in md_output
    assert "ticket_77" in md_output
    assert "CRITICAL" in md_output
