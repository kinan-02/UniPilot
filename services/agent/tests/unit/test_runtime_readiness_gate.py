"""Unit tests for runtime readiness gate (Phase 25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.agent.readiness.manifest_loader import load_runtime_readiness_manifest
from app.agent.readiness.runtime_gate import evaluate_runtime_readiness_gate
from app.agent.readiness.schemas import RuntimeReadinessGateInput, RuntimeReadinessManifest
from app.config import Settings

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "promotion_readiness_manifest.test.json"
_NOW = datetime(2026, 7, 6, tzinfo=timezone.utc)


def _settings(**overrides: object) -> Settings:
    base = {
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
        "AGENT_RUNTIME_READINESS_REQUIRE_HUMAN_REVIEW": True,
        "AGENT_RUNTIME_READINESS_FAIL_CLOSED": True,
        "AGENT_RUNTIME_READINESS_MIN_LEVEL": "ready_for_limited_promotion",
        "AGENT_RUNTIME_READINESS_MAX_AGE_DAYS": 30,
    }
    base.update(overrides)
    return Settings(**base)


def _gate_input(**overrides: object) -> RuntimeReadinessGateInput:
    defaults = {
        "candidate_id": "synthesis_text_promotion.course_question_workflow",
        "requested_scope": "course_question_workflow",
        "required_level": "ready_for_limited_promotion",
        "require_human_review": True,
    }
    defaults.update(overrides)
    return RuntimeReadinessGateInput(**defaults)


def test_gate_disabled_allows() -> None:
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=None,
        settings=_settings(AGENT_RUNTIME_READINESS_GATE_ENABLED=False),
        now=_NOW,
    )
    assert decision.allowed is True
    assert "gate_disabled" in decision.reasons


def test_enabled_missing_manifest_blocks_when_fail_closed() -> None:
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=None,
        settings=_settings(),
        now=_NOW,
    )
    assert decision.allowed is False
    assert "manifest_missing" in decision.reasons


def test_enabled_missing_candidate_blocks() -> None:
    manifest = load_runtime_readiness_manifest(_FIXTURE)
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(candidate_id="missing.candidate"),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert decision.allowed is False
    assert "candidate_not_found" in decision.reasons


def test_approved_false_blocks() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "reviewedAt": "2026-07-06T00:00:00Z",
            "reviewedBy": "human",
            "candidates": [
                {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "level": "ready_for_limited_promotion",
                    "approved": False,
                    "scope": ["course_question_workflow"],
                }
            ],
        }
    )
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert "candidate_not_approved" in decision.reasons


def test_missing_human_review_blocks_when_required() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "candidates": [
                {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "level": "ready_for_limited_promotion",
                    "approved": True,
                    "scope": ["course_question_workflow"],
                }
            ],
        }
    )
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert "human_review_missing" in decision.reasons


def test_level_below_required_blocks() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "reviewedAt": "2026-07-06T00:00:00Z",
            "reviewedBy": "human",
            "candidates": [
                {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "level": "ready_for_shadow",
                    "approved": True,
                    "scope": ["course_question_workflow"],
                }
            ],
        }
    )
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert "level_below_required" in decision.reasons


def test_expired_candidate_blocks() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "reviewedAt": "2026-07-06T00:00:00Z",
            "reviewedBy": "human",
            "candidates": [
                {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "level": "ready_for_limited_promotion",
                    "approved": True,
                    "scope": ["course_question_workflow"],
                    "expiresAt": "2026-01-01T00:00:00Z",
                }
            ],
        }
    )
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert "candidate_expired" in decision.reasons


def test_stale_manifest_blocks() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "reviewedAt": "2020-01-01T00:00:00Z",
            "reviewedBy": "human",
            "candidates": [
                {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "level": "ready_for_limited_promotion",
                    "approved": True,
                    "scope": ["course_question_workflow"],
                }
            ],
        }
    )
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=manifest,
        settings=_settings(AGENT_RUNTIME_READINESS_MAX_AGE_DAYS=30),
        now=_NOW,
    )
    assert "manifest_stale" in decision.reasons


def test_scope_mismatch_blocks() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "reviewedAt": "2026-07-06T00:00:00Z",
            "reviewedBy": "human",
            "candidates": [
                {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "level": "ready_for_limited_promotion",
                    "approved": True,
                    "scope": ["graduation_progress_workflow"],
                }
            ],
        }
    )
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(requested_scope="course_question_workflow"),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert "scope_mismatch" in decision.reasons


def test_valid_reviewed_candidate_allows() -> None:
    manifest = load_runtime_readiness_manifest(_FIXTURE)
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert decision.allowed is True


def test_ready_for_broader_satisfies_ready_for_limited() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "reviewedAt": "2026-07-06T00:00:00Z",
            "reviewedBy": "human",
            "candidates": [
                {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "level": "ready_for_broader_promotion",
                    "approved": True,
                    "scope": ["course_question_workflow"],
                }
            ],
        }
    )
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(required_level="ready_for_limited_promotion"),
        manifest=manifest,
        settings=_settings(),
        now=_NOW,
    )
    assert decision.allowed is True


def test_malformed_manifest_never_crashes() -> None:
    decision = evaluate_runtime_readiness_gate(
        gate_input=_gate_input(),
        manifest=None,
        settings=_settings(AGENT_RUNTIME_READINESS_FAIL_CLOSED=False),
        now=_NOW,
    )
    assert decision.allowed is True
