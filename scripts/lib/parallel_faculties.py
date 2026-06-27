"""Multiprocessing helpers for per-faculty catalog verification scripts."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def default_worker_count(workers: int | None) -> int:
    if workers is not None and workers > 0:
        return workers
    cpu = os.cpu_count() or 4
    return max(1, min(cpu, 8))


def map_faculties_parallel(
    faculty_ids: Sequence[str],
    worker: Callable[[str], R],
    *,
    workers: int | None = None,
) -> list[R]:
    """Run ``worker(faculty_id)`` across faculties using a process pool."""
    ids = list(faculty_ids)
    if not ids:
        return []

    worker_count = min(default_worker_count(workers), len(ids))
    if worker_count == 1:
        return [worker(faculty_id) for faculty_id in ids]

    results: list[R | None] = [None] * len(ids)
    index_by_id = {faculty_id: index for index, faculty_id in enumerate(ids)}
    with ProcessPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(worker, faculty_id): faculty_id for faculty_id in ids}
        for future in as_completed(futures):
            faculty_id = futures[future]
            results[index_by_id[faculty_id]] = future.result()
    return [result for result in results if result is not None]


def flatten_results(nested: Iterable[Sequence[T]]) -> list[T]:
    return [item for group in nested for item in group]
