"""Unit tests for promotion readiness audit (Phase 28.2)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.agent.readiness.promotion_audit import audit_promotion_readiness
from app.config import Settings


def _write_manifest(path: Path, *, candidate_id: str, workflow: str, approved: bool = True, expires_at: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "schemaVersion": "1",
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "reviewedAt": now.isoformat().replace("+00:00", "Z"),
        "reviewedBy": "test-reviewer",
        "candidates": [
            {
                "candidateId": candidate_id,
                "level": "ready_for_limited_promotion",
                "approved": approved,
                "scope": [workflow],
                "expiresAt": expires_at,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_FAIL_CLOSED": True,
            "AGENT_RUNTIME_READINESS_REQUIRE_HUMAN_REVIEW": True,
            "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": False,
            "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "off",
            **overrides,
        }
    )


def test_missing_manifest_blocks(tmp_path: Path) -> None:
    report = audit_promotion_readiness(
        workflow_name="graduation_progress_workflow",
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        settings=_settings(),
        manifest_path=tmp_path / "missing.json",
    )
    assert report["finalDecision"] == "would_block"
    assert "manifest_missing" in report["blockReasons"]


def test_stale_manifest_blocks(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    old = datetime.now(timezone.utc) - timedelta(days=60)
    payload = {
        "schemaVersion": "1",
        "generatedAt": old.isoformat().replace("+00:00", "Z"),
        "reviewedAt": old.isoformat().replace("+00:00", "Z"),
        "reviewedBy": "test-reviewer",
        "candidates": [
            {
                "candidateId": "synthesis_text_promotion.graduation_progress_workflow",
                "level": "ready_for_limited_promotion",
                "approved": True,
                "scope": ["graduation_progress_workflow"],
            }
        ],
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    report = audit_promotion_readiness(
        workflow_name="graduation_progress_workflow",
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        settings=_settings(),
        manifest_path=manifest_path,
    )
    assert report["finalDecision"] == "would_block"
    assert "manifest_stale" in report["blockReasons"]


def test_expired_candidate_blocks(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    _write_manifest(
        manifest_path,
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        workflow="graduation_progress_workflow",
        expires_at=expired,
    )
    report = audit_promotion_readiness(
        workflow_name="graduation_progress_workflow",
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        settings=_settings(),
        manifest_path=manifest_path,
    )
    assert report["finalDecision"] == "would_block"
    assert "candidate_expired" in report["blockReasons"]


def test_scope_mismatch_blocks(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        workflow="course_question_workflow",
    )
    report = audit_promotion_readiness(
        workflow_name="graduation_progress_workflow",
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        settings=_settings(),
        manifest_path=manifest_path,
    )
    assert report["finalDecision"] == "would_block"
    assert "scope_mismatch" in report["blockReasons"]


def test_hard_workflow_ceiling_blocks_unsupported_workflow(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        candidate_id="synthesis_text_promotion.transcript_import_workflow",
        workflow="transcript_import_workflow",
    )
    report = audit_promotion_readiness(
        workflow_name="transcript_import_workflow",
        candidate_id="synthesis_text_promotion.transcript_import_workflow",
        settings=_settings(),
        manifest_path=manifest_path,
    )
    assert report["finalDecision"] == "would_block"
    assert "workflow_not_in_hard_ceiling" in report["blockReasons"]


def test_valid_approved_scoped_candidate_still_blocks_without_promotion_flags(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace("+00:00", "Z")
    _write_manifest(
        manifest_path,
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        workflow="graduation_progress_workflow",
        expires_at=expires,
    )
    report = audit_promotion_readiness(
        workflow_name="graduation_progress_workflow",
        candidate_id="synthesis_text_promotion.graduation_progress_workflow",
        settings=_settings(),
        manifest_path=manifest_path,
    )
    assert report["manifestExists"] is True
    assert report["candidateApproved"] is True
    assert report["scopeMatch"] is True
    assert report["runtimeGateAllowed"] is True
    assert report["finalDecision"] == "would_block"
    assert "synthesis_text_promotion_disabled" in report["blockReasons"]
