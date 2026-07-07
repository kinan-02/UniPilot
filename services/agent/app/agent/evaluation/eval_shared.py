"""Shared helpers for agent evaluation runners."""

from __future__ import annotations

from collections import Counter
from typing import Any


def filter_benchmark_cases(
    cases: list[dict[str, Any]],
    *,
    categories: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    filtered = cases
    if categories:
        allowed = {category.strip() for category in categories if category.strip()}
        filtered = [case for case in filtered if str(case.get("category") or "") in allowed]
    if limit > 0:
        filtered = filtered[:limit]
    return filtered


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status") or "unknown") for item in results)
    passed = status_counts.get("pass", 0)
    failed = status_counts.get("fail", 0)
    skipped = status_counts.get("skip", 0)
    executed = passed + failed
    pass_rate = (passed / executed) if executed else 0.0

    by_category: dict[str, dict[str, int]] = {}
    latencies = [
        float(item["latencyMs"])
        for item in results
        if item.get("status") in {"pass", "fail"} and item.get("latencyMs") is not None
    ]
    for item in results:
        category = str(item.get("category") or "uncategorized")
        bucket = by_category.setdefault(category, Counter())
        bucket[str(item.get("status") or "unknown")] += 1

    category_summary = {
        category: {
            "pass": counts.get("pass", 0),
            "fail": counts.get("fail", 0),
            "skip": counts.get("skip", 0),
        }
        for category, counts in sorted(by_category.items())
    }

    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "executed": executed,
        "passRate": round(pass_rate, 4),
        "latencyMs": {
            "p50": round(sorted(latencies)[len(latencies) // 2], 1) if latencies else 0,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 1)
            if latencies
            else 0,
            "max": round(max(latencies), 1) if latencies else 0,
        },
        "byCategory": category_summary,
    }
