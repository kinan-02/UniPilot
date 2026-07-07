"""Run the full RAG fine-tuning baseline pipeline with one progress bar."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.retrieval.embedding_service import reset_embeddings_client_cache
from app.retrieval.evaluation.progress import SingleBarProgress
from app.retrieval.evaluation.run_retrieval_eval import (
    _BENCHMARK_PATH,
    load_benchmark_cases,
    run_evaluation,
)
from app.retrieval.cache_warmup import resolve_wiki_root, warmup_retrieval_caches
from app.retrieval.evaluation.mongo_eval import close_eval_database
from app.retrieval.obsidian_wiki_indexer import reset_wiki_index_cache
from app.retrieval.profiles import reset_profile_config_cache
from app.retrieval.wiki_vector_index import (
    build_wiki_vector_index,
    estimate_index_build_cost,
    format_index_cache_loaded_message,
    load_index_from_cache,
    reset_wiki_vector_index_runtime_cache,
    resolve_cache_path,
)


def _index_batches_needed(*, wiki_root: str, settings: Any, force_rebuild: bool) -> int:
    if not settings.wiki_vector_index_enabled() or not settings.embeddings_available():
        return 0
    if not force_rebuild:
        cache_path = resolve_cache_path(settings)
        cached = load_index_from_cache(
            cache_path,
            wiki_root=wiki_root,
            model=settings.resolved_embedding_model(),
        )
        if cached is not None:
            return 0
    estimate = estimate_index_build_cost(wiki_root=wiki_root, settings=settings)
    return int(estimate.get("batchCount") or 0)


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


async def run_fine_tuning(
    *,
    benchmark_path: Path,
    output_path: Path,
    wiki_root: str,
    force_index_rebuild: bool,
    skip_index: bool,
    connect_mongo: bool,
    require_mongo: bool,
    progress: SingleBarProgress,
) -> dict[str, Any]:
    settings = get_settings()
    cases = load_benchmark_cases(benchmark_path)
    index_batches = 0 if skip_index else _index_batches_needed(
        wiki_root=wiki_root,
        settings=settings,
        force_rebuild=force_index_rebuild,
    )
    progress.set_phase("Preparing")

    index_meta: dict[str, Any] = {"skipped": skip_index, "batches": index_batches}
    if not skip_index and settings.embeddings_available() and settings.wiki_vector_index_enabled():
        if index_batches > 0:
            progress.set_phase("Embedding wiki index")

            def on_batch(batch_index: int, _total_batches: int) -> None:
                progress.set_phase(f"Embedding wiki index ({batch_index}/{_total_batches})")
                progress.advance(1)

            index = build_wiki_vector_index(
                wiki_root=wiki_root,
                settings=settings,
                force_rebuild=force_index_rebuild,
                on_batch_embedded=on_batch,
            )
            if index is None:
                raise RuntimeError("Wiki vector index build failed")
            index_meta.update(
                {
                    "chunkCount": len(index.entries),
                    "cachePath": settings.resolved_embedding_index_cache_path(),
                    "model": index.model,
                }
            )
        else:
            progress.set_phase("Using cached wiki index")
            index_meta["cacheHit"] = True
            warmup_retrieval_caches(
                wiki_root=wiki_root,
                settings=settings,
                load_vector_index=True,
                allow_index_build=False,
            )
            progress.advance(1)

    payload = await run_evaluation(
        benchmark_path=benchmark_path,
        progress=progress,
        connect_mongo=connect_mongo,
        require_mongo=require_mongo,
        skip_vector_index=skip_index,
    )
    payload["fineTuning"] = {
        "index": index_meta,
        "benchmarkPath": str(benchmark_path),
        "caseCount": len(cases),
    }

    progress.set_phase("Saving results")
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    progress.advance(1)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UniPilot RAG fine-tuning baseline")
    parser.add_argument("--benchmark", type=Path, default=_BENCHMARK_PATH)
    parser.add_argument("--output", type=Path, default=Path("retrieval_eval_results.json"))
    parser.add_argument("--wiki-root", type=Path, default=None)
    parser.add_argument("--force-index", action="store_true", help="Rebuild embedding index")
    parser.add_argument("--skip-index", action="store_true", help="Skip index build (eval only)")
    parser.add_argument("--no-progress", action="store_true", help="Disable the progress bar")
    parser.add_argument(
        "--no-mongo",
        action="store_true",
        help="Skip MongoDB offering eval cases",
    )
    parser.add_argument(
        "--require-mongo",
        action="store_true",
        help="Fail if MongoDB is not reachable",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    reset_profile_config_cache()
    reset_wiki_index_cache()
    reset_embeddings_client_cache()
    reset_wiki_vector_index_runtime_cache()

    settings = get_settings()
    wiki_root = resolve_wiki_root(
        str(args.wiki_root or settings.catalog_vault_wiki_path or "").strip()
    )
    if not wiki_root:
        raise SystemExit("Set CATALOG_VAULT_WIKI_PATH or pass --wiki-root")

    cache_path = resolve_cache_path(settings)
    cached_index = load_index_from_cache(
        cache_path,
        wiki_root=wiki_root,
        model=settings.resolved_embedding_model(),
    )
    if args.skip_index and cached_index is None:
        print(
            "Note: --skip-index will not rebuild the wiki vector index. "
            "Cache miss — eval uses per-query embeddings only (~331 API calls). "
            "Run once without --skip-index to rebuild the index.",
            flush=True,
        )
    elif cached_index is not None:
        print(format_index_cache_loaded_message(cached_index, cache_path), flush=True)
    elif not args.skip_index and settings.embeddings_available():
        print(
            "Wiki vector index cache miss for this wiki path — "
            "a full chunk embedding build will run (LLMod cost).",
            flush=True,
        )

    cases = load_benchmark_cases(args.benchmark)
    index_batches = 0 if args.skip_index else _index_batches_needed(
        wiki_root=wiki_root,
        settings=settings,
        force_rebuild=args.force_index,
    )
    total_steps = index_batches + len(cases) + 2
    defer_index_build = index_batches > 0

    progress = SingleBarProgress(
        total=total_steps,
        desc="RAG fine-tuning",
        disable=args.no_progress,
    )
    progress.set_phase(
        "Loading wiki chunks" if defer_index_build else "Warming retrieval caches"
    )
    warmup_retrieval_caches(
        wiki_root=wiki_root,
        settings=settings,
        load_vector_index=not args.skip_index and not defer_index_build,
        allow_index_build=False,
    )
    progress.advance(1)

    started = time.perf_counter()
    try:
        payload = asyncio.run(
            run_fine_tuning(
                benchmark_path=args.benchmark,
                output_path=args.output,
                wiki_root=wiki_root,
                force_index_rebuild=args.force_index,
                skip_index=args.skip_index,
                connect_mongo=not args.no_mongo,
                require_mongo=args.require_mongo,
                progress=progress,
            )
        )
    finally:
        progress.close()
        if not args.no_mongo:
            asyncio.run(close_eval_database())

    elapsed = time.perf_counter() - started
    SingleBarProgress.write(f"Completed in {_format_duration(elapsed)}")
    SingleBarProgress.write(json.dumps(payload["overall"], indent=2))
    SingleBarProgress.write(f"Results written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
