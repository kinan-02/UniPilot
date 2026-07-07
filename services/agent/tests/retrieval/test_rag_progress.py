"""Tests for single-bar tqdm progress helper."""

from __future__ import annotations

from app.retrieval.evaluation.progress import NullProgress, SingleBarProgress


def test_null_progress_is_noop():
    progress = NullProgress()
    progress.set_phase("test")
    progress.advance(3)
    progress.close()


def test_single_bar_progress_lifecycle():
    progress = SingleBarProgress(total=3, desc="test", disable=True)
    progress.set_phase("phase-1")
    progress.advance(1)
    progress.set_total(5)
    progress.advance(2)
    progress.close()
