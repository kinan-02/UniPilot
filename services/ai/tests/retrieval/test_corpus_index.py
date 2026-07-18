"""Tests for corpus statistics and the BM25 they feed."""

from __future__ import annotations

from app.retrieval.corpus_index import build_chunk_stats, build_corpus_index, get_corpus_index
from app.retrieval.obsidian_wiki_indexer import WikiChunk
from app.retrieval.reranker import bm25_score, tokenize


def _chunk(section_title: str, content: str, *, course_numbers: tuple[str, ...] = ()) -> WikiChunk:
    return WikiChunk(
        source_file=f"courses/{section_title.replace(' ', '-').lower()}.md",
        page_title="Page",
        section_title=section_title,
        heading_path=("Page", section_title),
        content=content,
        course_numbers_mentioned=course_numbers,
    )


# -- IDF -----------------------------------------------------------------


def test_idf_down_weights_a_term_present_in_every_document():
    """The retired scorer gave every matching token a floor of 1.0, so
    "the" counted as much as a course code."""
    corpus = build_corpus_index([_chunk(f"S{i}", "course course course") for i in range(20)])
    assert corpus.idf("course") < corpus.idf("nowhere")


def test_idf_is_neutral_without_corpus_statistics():
    """An empty index must degrade to term-frequency scoring, not zero everything."""
    corpus = build_corpus_index([])
    assert corpus.idf("anything") == 1.0


def test_rare_term_scores_above_common_term_at_equal_frequency():
    docs = [_chunk(f"Common{i}", "widget filler filler") for i in range(30)]
    docs.append(_chunk("Rare", "sprocket filler filler"))
    corpus = build_corpus_index(docs)
    rare = corpus.bm25(build_chunk_stats(_chunk("X", "sprocket filler filler")), ["sprocket"])
    common = corpus.bm25(build_chunk_stats(_chunk("X", "widget filler filler")), ["widget"])
    assert rare > common


# -- length normalization ------------------------------------------------


def test_length_normalization_stops_long_chunks_winning_on_length_alone():
    """Previously the score grew with content length, so a padded chunk
    outranked a focused one containing the same term once."""
    short = _chunk("Short", "prerequisites")
    long = _chunk("Long", "prerequisites " + "unrelated padding words here " * 60)
    corpus = build_corpus_index([short, long, *(_chunk(f"F{i}", "filler") for i in range(10))])
    q = ["prerequisites"]
    assert corpus.bm25(build_chunk_stats(short), q) > corpus.bm25(build_chunk_stats(long), q)


# -- course numbers ------------------------------------------------------


def test_course_number_boost_requires_an_exact_match():
    """It was `token in number`, so "0044" boosted every 0044xxxx course."""
    chunk = _chunk("Desc", "body text", course_numbers=("00440105",))
    corpus = build_corpus_index([chunk])
    exact = bm25_score(chunk, tokenize("00440105"), corpus=corpus)
    prefix = bm25_score(chunk, tokenize("0044"), corpus=corpus)
    assert exact > 0
    assert prefix == 0.0


def test_bm25_without_a_corpus_still_scores():
    """Callers holding chunks outside the indexed corpus must not get zeros."""
    chunk = _chunk("Desc", "discrete mathematics for computer science")
    assert bm25_score(chunk, tokenize("discrete mathematics")) > 0


# -- caching -------------------------------------------------------------


def test_get_corpus_index_is_empty_for_a_blank_root():
    index = get_corpus_index("")
    assert index.document_count == 0
    assert index.idf("x") == 1.0


def test_stats_for_falls_back_to_tokenizing_an_unknown_chunk():
    corpus = build_corpus_index([_chunk("Known", "known content here")])
    stranger = _chunk("Stranger", "entirely different words")
    stats = corpus.stats_for("not-a-real-vector-id", stranger)
    assert "entirely" in stats.body_tokens


def test_stats_for_returns_empty_when_the_chunk_is_unavailable():
    corpus = build_corpus_index([_chunk("Known", "known content here")])
    assert corpus.stats_for("missing").length == 0
