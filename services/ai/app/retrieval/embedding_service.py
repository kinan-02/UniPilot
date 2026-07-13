"""LLMod / OpenAI-compatible embedding client for hybrid wiki retrieval."""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import Settings, get_settings

if TYPE_CHECKING:
    from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

# `OpenAIEmbeddings` defaults `request_timeout` (aliased `timeout`) to `None`
# -- unbounded -- same gap `ChatLLMAdapter`'s own callers had (see
# reasoning/llm_adapter.py, interpret_text.py, compose_answer.py). Found via
# a live-eval run: once EMBEDDING_API_KEY was configured, a single stalled
# embeddings call made a turn's own `asyncio.wait_for(..., timeout=300)`
# elapse at 463s instead of cutting off at 300s -- because this call chain
# is fully synchronous (see search_knowledge.py's `asyncio.to_thread` fix),
# so the outer timeout can only fire once the blocking call itself finally
# returns, however long that takes without a bound of its own.
_EMBEDDING_TIMEOUT_SECONDS = 15.0


@lru_cache(maxsize=1)
def get_embeddings_client() -> OpenAIEmbeddings | None:
    """Return a cached LangChain embeddings client, or None when not configured."""
    cfg = get_settings()
    if not cfg.embeddings_available():
        return None

    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        api_key=cfg.resolved_embedding_api_key(),
        base_url=cfg.resolved_embedding_base_url(),
        model=cfg.resolved_embedding_model(),
        timeout=_EMBEDDING_TIMEOUT_SECONDS,
    )


def reset_embeddings_client_cache() -> None:
    get_embeddings_client.cache_clear()
    embed_query_cached.cache_clear()


@lru_cache(maxsize=1024)
def embed_query_cached(
    query: str,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[float, ...] | None:
    """Cached query embedding keyed by credentials + model (safe for benchmark loops)."""
    if not api_key:
        return None
    from langchain_openai import OpenAIEmbeddings

    client = OpenAIEmbeddings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=_EMBEDDING_TIMEOUT_SECONDS,
    )
    try:
        vector = client.embed_query(query or "")
        return tuple(float(value) for value in vector) if vector else None
    except Exception:  # noqa: BLE001
        logger.exception("embedding_query_failed")
        return None


def embed_query(text: str, *, settings: Settings | None = None) -> list[float] | None:
    cfg = settings or get_settings()
    if not cfg.embeddings_available():
        return None
    cached = embed_query_cached(
        text or "",
        cfg.resolved_embedding_api_key(),
        cfg.resolved_embedding_base_url(),
        cfg.resolved_embedding_model(),
    )
    return list(cached) if cached else None


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def embed_documents(
    texts: list[str],
    *,
    settings: Settings | None = None,
) -> list[list[float]] | None:
    cfg = settings or get_settings()
    if not cfg.embeddings_available() or not texts:
        return None
    client = get_embeddings_client()
    if client is None:
        return None
    try:
        vectors = client.embed_documents(texts)
        return [list(vector) for vector in vectors] if vectors else None
    except Exception:  # noqa: BLE001
        logger.exception("embedding_documents_failed")
        return None


def build_semantic_score_map(
    *,
    query: str,
    document_texts: list[str],
    settings: Settings | None = None,
) -> dict[int, float] | None:
    """Embed query + documents and return cosine scores keyed by document index."""
    if not document_texts:
        return None

    vectors = embed_documents([query, *document_texts], settings=settings)
    if not vectors or len(vectors) != len(document_texts) + 1:
        return None

    query_vector = vectors[0]
    return {
        index: cosine_similarity(query_vector, document_vector)
        for index, document_vector in enumerate(vectors[1:])
    }
