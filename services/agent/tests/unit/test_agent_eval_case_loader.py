"""Unit tests for offline eval case loader (Phase 23)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.evaluation.case_loader import load_eval_cases

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eval_cases"


def test_loads_single_json_case(tmp_path: Path) -> None:
    path = tmp_path / "one.json"
    path.write_text(
        json.dumps(
            {
                "id": "z_case",
                "name": "Z",
                "kind": "course_question",
                "user_message": "hi",
            }
        ),
        encoding="utf-8",
    )
    cases = load_eval_cases(path)
    assert len(cases) == 1
    assert cases[0].id == "z_case"


def test_loads_jsonl_cases(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"id": "a", "name": "A", "kind": "course_question", "user_message": "a"}),
                json.dumps({"id": "b", "name": "B", "kind": "course_question", "user_message": "b"}),
            ]
        ),
        encoding="utf-8",
    )
    cases = load_eval_cases(path)
    assert [c.id for c in cases] == ["a", "b"]


def test_loads_directory_deterministically() -> None:
    cases = load_eval_cases(_FIXTURES)
    assert len(cases) >= 15
    assert cases == sorted(cases, key=lambda c: c.id)


def test_rejects_malformed_case(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"name": "missing id"}), encoding="utf-8")
    with pytest.raises(Exception):
        load_eval_cases(path)


def test_rejects_forbidden_payload(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "id": "bad",
                "name": "bad",
                "kind": "course_question",
                "user_message": "x",
                "raw_context": "nope",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        load_eval_cases(path)


def test_never_executes_fixture_content(tmp_path: Path) -> None:
    path = tmp_path / "safe.json"
    path.write_text(
        json.dumps(
            {
                "id": "safe",
                "name": "safe",
                "kind": "course_question",
                "user_message": "__import__('os').system('echo pwned')",
            }
        ),
        encoding="utf-8",
    )
    cases = load_eval_cases(path)
    assert cases[0].user_message.startswith("__import__")


def test_loader_does_not_call_network_or_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network_or_llm_called")

    monkeypatch.setattr("socket.socket", _fail)
    cases = load_eval_cases(_FIXTURES)
    assert cases
