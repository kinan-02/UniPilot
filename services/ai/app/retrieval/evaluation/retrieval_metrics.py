"""Retrieval evaluation metrics (Agent_RAG_tuning.md §19)."""

from __future__ import annotations

import math
import re
from typing import Any

_WILDCARD = re.compile(r"\*$")


def _matches_pattern(source_id: str, pattern: str) -> bool:
    if _WILDCARD.search(pattern):
        prefix = pattern.replace("*", "")
        return source_id.startswith(prefix)
    return source_id == pattern or pattern in source_id


def hit_at_k(retrieved: list[str], required: list[str], k: int) -> float:
    if not required:
        return 1.0
    top = retrieved[:k]
    return 1.0 if any(_matches_pattern(item, req) for item in top for req in required) else 0.0


def recall_at_k(retrieved: list[str], required: list[str], k: int) -> float:
    if not required:
        return 1.0
    top = retrieved[:k]
    hits = sum(
        1
        for req in required
        if any(_matches_pattern(item, req) for item in top)
    )
    return hits / len(required)


def precision_at_k(retrieved: list[str], required: list[str], k: int) -> float:
    if not retrieved[:k]:
        return 0.0
    top = retrieved[:k]
    hits = sum(
        1
        for item in top
        if any(_matches_pattern(item, req) for req in required)
    )
    return hits / len(top)


def reciprocal_rank(retrieved: list[str], required: list[str]) -> float:
    for index, item in enumerate(retrieved, start=1):
        if any(_matches_pattern(item, req) for req in required):
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved: list[str], required: list[str], k: int) -> float:
    if not required:
        return 1.0
    dcg = 0.0
    for index, item in enumerate(retrieved[:k], start=1):
        rel = 1.0 if any(_matches_pattern(item, req) for req in required) else 0.0
        if rel:
            dcg += rel / math.log2(index + 1)
    ideal_hits = min(len(required), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def wrong_source_rate(retrieved: list[str], negative: list[str]) -> float:
    if not negative or not retrieved:
        return 0.0
    violations = sum(
        1
        for item in retrieved
        if any(_matches_pattern(item, bad) for bad in negative)
    )
    return violations / len(retrieved)


def aggregate_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not case_results:
        return {}
    keys = ["hitAt1", "hitAt3", "recallAt5", "recallAt8", "mrr", "ndcgAt8", "wrongSourceRate"]
    summary: dict[str, Any] = {"caseCount": len(case_results)}
    for key in keys:
        values = [float(result.get(key, 0.0)) for result in case_results]
        summary[key] = round(sum(values) / len(values), 4)
    latencies = [int(result.get("latencyMs") or 0) for result in case_results]
    if latencies:
        summary["avgLatencyMs"] = int(sum(latencies) / len(latencies))
    return summary
