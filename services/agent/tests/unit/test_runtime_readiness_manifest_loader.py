"""Unit tests for runtime readiness manifest loader (Phase 25)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.readiness.manifest_loader import load_runtime_readiness_manifest

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "promotion_readiness_manifest.test.json"


def test_loads_valid_manifest() -> None:
    manifest = load_runtime_readiness_manifest(_FIXTURE)
    assert manifest is not None
    assert manifest.reviewed_by == "test-reviewer"
    assert manifest.candidates[0].candidate_id.startswith("synthesis_text_promotion.")


def test_returns_none_on_missing_file(tmp_path: Path) -> None:
    assert load_runtime_readiness_manifest(tmp_path / "missing.json") is None


def test_rejects_malformed_manifest(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"candidates": "not-a-list"}), encoding="utf-8")
    assert load_runtime_readiness_manifest(path) is None


def test_deterministic_candidate_ordering() -> None:
    manifest = load_runtime_readiness_manifest(_FIXTURE)
    assert manifest is not None
    ids = [item.candidate_id for item in manifest.candidates]
    assert ids == sorted(ids)


def test_does_not_execute_content(tmp_path: Path) -> None:
    path = tmp_path / "safe.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1",
                "reviewedAt": "2026-07-06T00:00:00Z",
                "reviewedBy": "__import__('os').system('echo pwned')",
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )
    manifest = load_runtime_readiness_manifest(path)
    assert manifest is not None
    assert "pwned" in (manifest.reviewed_by or "")


def test_loader_does_not_call_network_or_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network_or_llm_called")

    monkeypatch.setattr("socket.socket", _fail)
    manifest = load_runtime_readiness_manifest(_FIXTURE)
    assert manifest is not None
