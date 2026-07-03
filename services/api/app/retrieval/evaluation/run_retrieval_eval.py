"""Run retrieval benchmark evaluation (Agent_RAG_tuning.md §21)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.retrieval.evaluation.retrieval_metrics import (
    aggregate_metrics,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    wrong_source_rate,
)
from app.retrieval.cache_warmup import warmup_retrieval_caches
from app.retrieval.evaluation.benchmark_offerings_seed import (
    audit_benchmark_offerings_coverage,
    seed_benchmark_offerings as upsert_benchmark_offerings,
)
from app.retrieval.evaluation.mongo_eval import close_eval_database, resolve_eval_database
from app.retrieval.hybrid_wiki_retriever import retrieve_wiki_context_with_profile
from app.retrieval.offerings_retriever import retrieve_offerings_context
from app.retrieval.profiles import get_profile, reset_profile_config_cache
from app.retrieval.evaluation.progress import NullProgress, ProgressReporter, SingleBarProgress
from app.retrieval.wiki_vector_index import (
    estimate_index_build_cost,
    estimate_query_embedding_cost,
    get_wiki_vector_index,
)


_BENCHMARK_PATH = Path(__file__).with_name("benchmark_cases.jsonl")


def load_benchmark_cases(path: Path | None = None) -> list[dict[str, Any]]:
    benchmark = path or _BENCHMARK_PATH
    cases: list[dict[str, Any]] = []
    for line in benchmark.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    return cases


def _provenance_source_ids(records: list[Any]) -> list[str]:
    ids: list[str] = []
    for record in records:
        source_id = getattr(record, "source_id", None)
        if source_id:
            ids.append(str(source_id))
    return ids


async def evaluate_wiki_case(case: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(case.get("profile") or "fallback_academic_search")
    profile = get_profile(profile_name)
    user_context = {
        "profile": {
            "track": (case.get("metadataContext") or {}).get("track"),
            "catalogYear": (case.get("metadataContext") or {}).get("catalogYear"),
            "degreeProgram": (case.get("metadataContext") or {}).get("degreeProgram"),
        }
    }
    entities = dict(case.get("entities") or {})
    snippets, _records, metadata = await retrieve_wiki_context_with_profile(
        query=str(case.get("query") or ""),
        user_context=user_context,
        entities=entities,
        profile=profile,
    )
    retrieved_ids = list(metadata.get("sourceIds") or [])
    required = list(case.get("mustRetrieve") or [])
    negative = list(case.get("negativeSources") or [])

    return {
        "id": case.get("id"),
        "evalType": "wiki",
        "profile": profile_name,
        "retrieved": retrieved_ids,
        "hitAt1": hit_at_k(retrieved_ids, required, 1),
        "hitAt3": hit_at_k(retrieved_ids, required, 3),
        "recallAt5": recall_at_k(retrieved_ids, required, 5),
        "recallAt8": recall_at_k(retrieved_ids, required, 8),
        "precisionAt5": precision_at_k(retrieved_ids, required, 5),
        "mrr": reciprocal_rank(retrieved_ids, required),
        "ndcgAt8": ndcg_at_k(retrieved_ids, required, 8),
        "wrongSourceRate": wrong_source_rate(retrieved_ids, negative),
        "latencyMs": metadata.get("latencyMs"),
        "snippetCount": len(snippets),
        "fallbackUsed": metadata.get("fallbackUsed"),
        "semanticMethod": metadata.get("semanticMethod"),
        "vectorIndex": metadata.get("vectorIndex"),
    }


async def evaluate_offering_case(
    case: dict[str, Any],
    *,
    database: Any | None,
) -> dict[str, Any]:
    profile_name = str(case.get("profile") or "semester_offering_lookup")
    entities = dict(case.get("entities") or {})
    retrieved_ids: list[str] = []
    if database is not None:
        _academic, records = await retrieve_offerings_context(
            database,
            queries=[entities],
            entities=entities,
        )
        retrieved_ids = _provenance_source_ids(records)

    required = list(case.get("mustRetrieve") or [])
    negative = list(case.get("negativeSources") or [])
    return {
        "id": case.get("id"),
        "evalType": "offering",
        "profile": profile_name,
        "retrieved": retrieved_ids,
        "hitAt1": hit_at_k(retrieved_ids, required, 1),
        "hitAt3": hit_at_k(retrieved_ids, required, 3),
        "recallAt5": recall_at_k(retrieved_ids, required, 5),
        "recallAt8": recall_at_k(retrieved_ids, required, 8),
        "precisionAt5": precision_at_k(retrieved_ids, required, 5),
        "mrr": reciprocal_rank(retrieved_ids, required),
        "ndcgAt8": ndcg_at_k(retrieved_ids, required, 8),
        "wrongSourceRate": wrong_source_rate(retrieved_ids, negative),
        "skipped": database is None,
    }


def build_cost_estimate(*, case_count: int, wiki_root: str | None) -> dict[str, Any]:
    settings = get_settings()
    estimate: dict[str, Any] = {
        "embeddingModel": settings.resolved_embedding_model(),
        "embeddingProvider": "llmod",
        "benchmarkCases": case_count,
        "notes": [
            "LLM (DeepSeek via OPENAI_*) is not used by retrieval eval.",
            "Costs below are embedding-only via EMBEDDING_* settings.",
        ],
    }
    if wiki_root:
        index_cost = estimate_index_build_cost(wiki_root=wiki_root, settings=settings)
        estimate["indexBuild"] = index_cost
        warm_index = get_wiki_vector_index(wiki_root=wiki_root, settings=settings) is not None
        estimate["vectorIndexWarm"] = warm_index
        wiki_cases = case_count
        estimate["evalQueryEmbeddings"] = estimate_query_embedding_cost(query_count=wiki_cases)
        if not warm_index:
            estimate["warning"] = (
                "Vector index not warm; eval may batch-embed candidates per case "
                "(much more expensive). Run build_wiki_vector_index first."
            )
    return estimate


async def run_evaluation(
    *,
    benchmark_path: Path | None = None,
    database: Any | None = None,
    connect_mongo: bool = True,
    require_mongo: bool = False,
    skip_vector_index: bool = False,
    seed_benchmark_offerings: bool = False,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    reporter = progress or NullProgress()
    reset_profile_config_cache()
    settings = get_settings()
    wiki_path = warmup_retrieval_caches(
        settings=settings,
        load_vector_index=not skip_vector_index,
        allow_index_build=not skip_vector_index,
    )
    cases = load_benchmark_cases(benchmark_path)

    eval_database = database
    if eval_database is None and connect_mongo:
        eval_database = await resolve_eval_database(settings=settings, require=require_mongo)

    offerings_seeded = 0
    offerings_coverage: dict[str, Any] | None = None
    if eval_database is not None:
        offerings_coverage = await audit_benchmark_offerings_coverage(
            eval_database,
            benchmark_path=benchmark_path,
            settings=settings,
        )
        if seed_benchmark_offerings:
            offerings_seeded = await upsert_benchmark_offerings(
                eval_database,
                benchmark_path=benchmark_path,
                settings=settings,
            )
            offerings_coverage = await audit_benchmark_offerings_coverage(
                eval_database,
                benchmark_path=benchmark_path,
                settings=settings,
            )
        elif offerings_coverage["caseCount"] > 0 and (
            offerings_coverage["resolvedCount"] < offerings_coverage["caseCount"]
        ):
            missing = offerings_coverage["caseCount"] - offerings_coverage["resolvedCount"]
            total = offerings_coverage["caseCount"]
            resolved = offerings_coverage["resolvedCount"]
            print(
                f"Warning: offering benchmark coverage {resolved}/{total} via Mongo/JSON. "
                "Import catalog offerings (data-engineering promotion) or set TECHNION_RAW_DIR. "
                "Use --seed-benchmark-offerings only for local CI without catalog data.",
                flush=True,
            )

    results: list[dict[str, Any]] = []
    reporter.set_phase("Evaluating benchmark")
    for case in cases:
        eval_type = str(case.get("evalType") or "wiki")
        if eval_type == "offering":
            results.append(await evaluate_offering_case(case, database=eval_database))
        else:
            results.append(await evaluate_wiki_case(case))
        reporter.advance(1)

    offering_results = [result for result in results if result.get("evalType") == "offering"]
    offering_skipped = sum(1 for result in offering_results if result.get("skipped"))

    by_profile: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_profile.setdefault(str(result["profile"]), []).append(result)

    by_eval_type: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_eval_type.setdefault(str(result.get("evalType") or "wiki"), []).append(result)

    return {
        "environment": {
            "wikiPathConfigured": bool(wiki_path),
            "wikiPath": wiki_path or None,
            "embeddingsConfigured": settings.embeddings_available(),
            "vectorIndexEnabled": settings.wiki_vector_index_enabled(),
            "vectorIndexWarm": bool(wiki_path and get_wiki_vector_index(wiki_root=wiki_path, settings=settings)),
            "mongoConfigured": bool((settings.mongo_uri or "").strip()),
            "mongoConnected": eval_database is not None,
            "offeringCaseCount": len(offering_results),
            "offeringCasesSkipped": offering_skipped,
            "benchmarkOfferingsSeeded": offerings_seeded,
            "offeringsCoverage": offerings_coverage,
        },
        "overall": aggregate_metrics(results),
        "byProfile": {name: aggregate_metrics(items) for name, items in sorted(by_profile.items())},
        "byEvalType": {name: aggregate_metrics(items) for name, items in sorted(by_eval_type.items())},
        "costEstimate": build_cost_estimate(case_count=len(cases), wiki_root=wiki_path or None),
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UniPilot retrieval benchmark")
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=_BENCHMARK_PATH,
        help="Path to benchmark_cases.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("retrieval_eval_results.json"),
        help="Output JSON path",
    )
    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Print embedding cost estimate and exit (no API calls)",
    )
    parser.add_argument(
        "--profiles-only",
        action="store_true",
        help="Print per-profile metrics summary to stdout",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the single progress bar",
    )
    parser.add_argument(
        "--no-mongo",
        action="store_true",
        help="Skip MongoDB offering eval cases",
    )
    parser.add_argument(
        "--require-mongo",
        action="store_true",
        help="Fail if MongoDB is not reachable (needed for offering cases)",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Do not build/load wiki vector index (query embeddings only; cheaper)",
    )
    parser.add_argument(
        "--seed-benchmark-offerings",
        action="store_true",
        help="DEV/CI only: upsert synthetic offerings (use real imported catalog in Mongo instead)",
    )
    args = parser.parse_args()

    import asyncio

    if args.estimate_cost:
        settings = get_settings()
        cases = load_benchmark_cases(args.benchmark)
        wiki_path = (settings.catalog_vault_wiki_path or "").strip()
        print(json.dumps(build_cost_estimate(case_count=len(cases), wiki_root=wiki_path or None), indent=2))
        return

    cases = load_benchmark_cases(args.benchmark)
    progress = SingleBarProgress(
        total=len(cases),
        desc="Retrieval eval",
        disable=args.no_progress,
    )
    try:
        payload = asyncio.run(
            run_evaluation(
                benchmark_path=args.benchmark,
                progress=progress,
                connect_mongo=not args.no_mongo,
                require_mongo=args.require_mongo,
                skip_vector_index=args.skip_index,
                seed_benchmark_offerings=args.seed_benchmark_offerings,
            )
        )
    finally:
        progress.close()
        if not args.no_mongo:
            asyncio.run(close_eval_database())
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.profiles_only:
        print(json.dumps(payload["byProfile"], indent=2))
    else:
        print(json.dumps(payload["overall"], indent=2))
        print(json.dumps(payload["byProfile"], indent=2))


if __name__ == "__main__":
    main()
