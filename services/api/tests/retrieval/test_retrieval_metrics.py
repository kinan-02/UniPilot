"""Unit tests for retrieval evaluation metrics."""

from app.retrieval.evaluation.retrieval_metrics import (
    aggregate_metrics,
    hit_at_k,
    ndcg_at_k,
    reciprocal_rank,
    wrong_source_rate,
)


def test_hit_at_k_exact_match():
    assert hit_at_k(["course:234218", "course:123"], ["course:234218"], 1) == 1.0
    assert hit_at_k(["course:123"], ["course:234218"], 1) == 0.0


def test_wrong_source_rate_counts_negatives():
    rate = wrong_source_rate(
        ["offering:2025-2:234218", "wiki:course:234218"],
        ["offering:2025-1:234218"],
    )
    assert rate == 0.0


def test_reciprocal_rank_and_ndcg():
    retrieved = ["wiki:a", "course:234218", "wiki:b"]
    required = ["course:234218"]
    assert reciprocal_rank(retrieved, required) == 0.5
    assert ndcg_at_k(retrieved, required, 3) > 0


def test_aggregate_metrics_averages():
    summary = aggregate_metrics(
        [
            {"hitAt1": 1.0, "recallAt5": 0.5, "mrr": 1.0, "ndcgAt8": 0.8, "wrongSourceRate": 0.0, "latencyMs": 100},
            {"hitAt1": 0.0, "recallAt5": 1.0, "mrr": 0.5, "ndcgAt8": 0.6, "wrongSourceRate": 0.1, "latencyMs": 200},
        ]
    )
    assert summary["caseCount"] == 2
    assert summary["hitAt1"] == 0.5
    assert summary["avgLatencyMs"] == 150
