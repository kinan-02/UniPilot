"""Build or refresh the cached wiki embedding index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.retrieval.embedding_service import reset_embeddings_client_cache
from app.retrieval.evaluation.progress import SingleBarProgress
from app.retrieval.obsidian_wiki_indexer import reset_wiki_index_cache
from app.retrieval.cache_warmup import resolve_wiki_root
from app.retrieval.wiki_vector_index import (
    backup_index_cache,
    build_wiki_vector_index,
    estimate_index_build_cost,
    reset_wiki_vector_index_runtime_cache,
    resolve_cache_path,
    restore_index_cache_from_backup,
    verify_index_cache,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build UniPilot wiki vector index")
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=None,
        help="Wiki root (defaults to CATALOG_VAULT_WIKI_PATH)",
    )
    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Print token estimate and exit without calling the embedding API",
    )
    parser.add_argument("--force", action="store_true", help="Rebuild even if cache exists")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify cache load (primary + backups) and exit",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a timestamped backup of the current compact cache",
    )
    parser.add_argument(
        "--restore-latest",
        action="store_true",
        help="Restore primary compact cache from latest backup",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_embeddings_client_cache()
    reset_wiki_vector_index_runtime_cache()

    settings = get_settings()
    wiki_root = resolve_wiki_root(str(args.wiki_root or settings.resolved_academic_wiki_path() or "").strip())
    if not wiki_root:
        raise SystemExit("Set ACADEMIC_WIKI_PATH or pass --wiki-root")

    cache_path = resolve_cache_path(settings)

    if args.verify:
        report = verify_index_cache(
            cache_path=cache_path,
            wiki_root=wiki_root,
            settings=settings,
        )
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report.get("ok") else 1)

    if args.backup:
        backup_path = backup_index_cache(cache_path=cache_path, settings=settings)
        print(
            json.dumps(
                {
                    "status": "ok" if backup_path is not None else "missing",
                    "backupPath": str(backup_path) if backup_path is not None else None,
                    "cachePath": str(cache_path),
                },
                indent=2,
            )
        )
        return

    if args.restore_latest:
        restored = restore_index_cache_from_backup(cache_path=cache_path, settings=settings)
        if restored is None:
            raise SystemExit("No backup available to restore")
        report = verify_index_cache(
            cache_path=cache_path,
            wiki_root=wiki_root,
            settings=settings,
        )
        print(json.dumps({"status": "ok", "restoredTo": str(restored), **report}, indent=2))
        return

    if args.estimate_cost:
        print(json.dumps(estimate_index_build_cost(wiki_root=wiki_root, settings=settings), indent=2))
        return

    if not settings.embeddings_available():
        raise SystemExit("EMBEDDING_API_KEY is required to build the wiki vector index")

    estimate = estimate_index_build_cost(wiki_root=wiki_root, settings=settings)
    total_batches = int(estimate.get("batchCount") or 0)
    progress = SingleBarProgress(
        total=max(1, total_batches or 1),
        desc="Wiki index build",
        disable=not sys.stderr.isatty(),
    )

    def on_batch(batch_index: int, batch_total: int) -> None:
        progress.set_phase(f"Embedding wiki index ({batch_index}/{batch_total})")
        progress.advance(1)

    try:
        if total_batches == 0:
            progress.set_phase("Using cached wiki index")
            progress.advance(1)
        index = build_wiki_vector_index(
            wiki_root=wiki_root,
            settings=settings,
            force_rebuild=args.force,
            on_batch_embedded=on_batch if total_batches > 0 else None,
        )
    finally:
        progress.close()
    if index is None:
        raise SystemExit("Index build failed")
    print(
        json.dumps(
            {
                "status": "ok",
                "chunkCount": len(index.entries),
                "model": index.model,
                "cachePath": settings.resolved_embedding_index_cache_path(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
