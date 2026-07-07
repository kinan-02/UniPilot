"""Tests for replay eval progress reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.evaluation.case_loader import load_eval_cases
from app.agent.evaluation.replay_runner import run_eval_cases
from app.retrieval.evaluation.progress import NullProgress

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eval_cases"


class _RecordingProgress:
    def __init__(self) -> None:
        self.phases: list[str] = []
        self.advanced = 0
        self.total: int | None = None
        self.closed = False

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)

    def advance(self, n: int = 1) -> None:
        self.advanced += n

    def set_total(self, total: int) -> None:
        self.total = total

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_run_eval_cases_updates_progress_reporter() -> None:
    cases = load_eval_cases(_FIXTURES)
    progress = _RecordingProgress()

    results = await run_eval_cases(cases, mode="gates_only", progress=progress)

    assert len(results) == len(cases)
    assert progress.total == len(cases)
    assert progress.advanced == len(cases)
    assert progress.phases
    assert progress.phases[0].startswith("Agent replay (gates_only)")
    assert any(case.id in phase for case, phase in zip(cases, progress.phases[1:], strict=False))


@pytest.mark.asyncio
async def test_run_eval_cases_defaults_to_null_progress() -> None:
    cases = load_eval_cases(_FIXTURES)
    results = await run_eval_cases(cases, mode="gates_only", progress=NullProgress())
    assert len(results) == len(cases)
