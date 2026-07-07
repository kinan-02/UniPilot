"""Unit tests for eval suite loader (Phase 24)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.evaluation.suite_loader import load_eval_suites

_SUITES = Path(__file__).resolve().parents[1] / "fixtures" / "eval_suites"


def test_loads_single_suite_json(tmp_path: Path) -> None:
    path = tmp_path / "one.json"
    path.write_text(
        json.dumps({"id": "z_suite", "name": "Z", "purpose": "core_regression"}),
        encoding="utf-8",
    )
    suites = load_eval_suites(path)
    assert len(suites) == 1
    assert suites[0].id == "z_suite"


def test_loads_jsonl_suites(tmp_path: Path) -> None:
    path = tmp_path / "suites.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"id": "a", "name": "A", "purpose": "core_regression"}),
                json.dumps({"id": "b", "name": "B", "purpose": "write_safety"}),
            ]
        ),
        encoding="utf-8",
    )
    suites = load_eval_suites(path)
    assert [s.id for s in suites] == ["a", "b"]


def test_loads_directory_deterministically() -> None:
    suites = load_eval_suites(_SUITES)
    assert len(suites) >= 10
    assert suites == sorted(suites, key=lambda s: s.id)


def test_rejects_malformed_suite(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"name": "missing id"}), encoding="utf-8")
    with pytest.raises(Exception):
        load_eval_suites(path)


def test_does_not_execute_fixture_content(tmp_path: Path) -> None:
    path = tmp_path / "safe.json"
    path.write_text(
        json.dumps(
            {
                "id": "safe",
                "name": "safe",
                "purpose": "core_regression",
                "description": "__import__('os').system('echo pwned')",
            }
        ),
        encoding="utf-8",
    )
    suites = load_eval_suites(path)
    assert "pwned" in suites[0].description


def test_loader_does_not_call_network_or_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network_or_llm_called")

    monkeypatch.setattr("socket.socket", _fail)
    suites = load_eval_suites(_SUITES)
    assert suites
