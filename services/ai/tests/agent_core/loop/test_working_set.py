"""Unit tests for working_set rendering helpers (§5). Pure, no LLM."""

from __future__ import annotations

from app.agent_core.loop.working_set import summarize_value


def test_summarize_scalar_list_reveals_its_values():
    # The fix: a list of scalars must SHOW it holds slottable values, not just a
    # bare "[list of N items]" (which a live sub-loop/forced-compose misread as
    # "no values here" and gave up on a list it actually held).
    out = summarize_value(["00940345", "00940704", "01040065", "02340221"])
    assert out.startswith("[list of 4 values:")
    assert "00940345" in out
    assert out.endswith("…]")  # sample capped at 3, rest elided


def test_summarize_short_scalar_list_has_no_ellipsis():
    assert summarize_value(["a", "b"]) == "[list of 2 values: a, b]"


def test_summarize_record_list_shows_fields_not_values():
    out = summarize_value([{"courseNumber": "X", "grade": 90}])
    assert out == "[list of 1 records, fields: ['courseNumber', 'grade']]"


def test_summarize_empty_list():
    assert summarize_value([]) == "[list of 0 items]"


def test_summarize_dict_shows_sorted_keys():
    assert summarize_value({"b": 1, "a": 2}) == "{dict with keys: ['a', 'b']}"


def test_summarize_scalar_is_json():
    assert summarize_value(92.5) == "92.5"


def test_summarize_clips_long_sample_values():
    long = "x" * 50
    out = summarize_value([long, long])
    assert ("x" * 24) in out and ("x" * 25) not in out  # each sample clipped to 24
