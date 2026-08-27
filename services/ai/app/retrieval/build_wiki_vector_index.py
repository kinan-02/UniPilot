"""Populate, migrate, or verify the Pinecone wiki vector index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.retrieval.cache_warmup import resolve_wiki_root
from app.retrieval.embedding_service import reset_embeddings_client_cache
from app.retrieval.evaluation.progress import SingleBarProgress
from app.retrieval.obsidian_wiki_indexer import reset_wiki_index_cache
from app.retrieval.vector_store import VectorStoreError
from app.retrieval.wiki_index_sync import (
    backfill_from_legacy_cache,
    reindex_wiki,
    verify_index,
)
from app.retrieval.wiki_vector_index import (
    estimate_index_build_cost,
    reset_wiki_vector_index_runtime_cache,
)

# Where the retired on-disk index was written before the Pinecone migration.
_DEFAULT_LEGACY_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "wiki_embedding_index.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the UniPilot wiki vector index (Pinecone)")
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=None,
        help="Wiki root (defaults to ACADEMIC_WIKI_PATH)",
    )
    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Print token estimate and exit without calling any API",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Compare Pinecone contents against the wiki on disk and exit",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Upload vectors from the retired on-disk cache instead of re-embedding (free)",
    )
    parser.add_argument(
        "--from-cache",
        type=Path,
        default=_DEFAULT_LEGACY_CACHE,
        help=f"Legacy cache path for --backfill (default: {_DEFAULT_LEGACY_CACHE})",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Keep Pinecone vectors whose chunk no longer exists on disk",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_embeddings_client_cache()
    reset_wiki_vector_index_runtime_cache()

    settings = get_settings()
    wiki_root = resolve_wiki_root(
        str(args.wiki_root or settings.resolved_academic_wiki_path() or "").strip()
    )
    if not wiki_root:
        raise SystemExit("Set ACADEMIC_WIKI_PATH or pass --wiki-root")

    if args.estimate_cost:
        print(json.dumps(estimate_index_build_cost(wiki_root=wiki_root, settings=settings), indent=2))
        return

    try:
        if args.verify:
            report = verify_index(wiki_root=wiki_root, settings=settings)
            print(json.dumps(report, indent=2))
            raise SystemExit(0 if report.get("ok") else 1)

        if args.backfill:
            report = backfill_from_legacy_cache(
                cache_path=args.from_cache,
                wiki_root=wiki_root,
                settings=settings,
                prune=not args.no_prune,
            )
            print(json.dumps(report, indent=2))
            return

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
            report = reindex_wiki(
                wiki_root=wiki_root,
                settings=settings,
                prune=not args.no_prune,
                on_batch_embedded=on_batch,
            )
        finally:
            progress.close()
        print(json.dumps(report, indent=2))
    except VectorStoreError as exc:
        raise SystemExit(f"Vector index operation failed: {exc}") from exc


if __name__ == "__main__":
    main()
