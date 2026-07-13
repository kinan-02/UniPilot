"""Tests for `normalize_structured_result` (app.agent_core.reasoning.result_normalizer).

`_recover_facts_list_and_missing_certainty` closes the single most common
schema-repair trigger found via a live-eval run: 53 of 96 schema-repair
calls across one night's cases were the model producing `facts` as a LIST
of individually-confidence-tagged items instead of the flat object the
schema requires, and omitting the separate top-level certainty_basis/
confidence entirely. This recovers that shape deterministically, with no
extra LLM call.
"""

from __future__ import annotations

from app.agent_core.reasoning.result_normalizer import normalize_structured_result

_RETRIEVAL_LIKE_SCHEMA = {
    "type": "object",
    "properties": {
        "certainty_basis": {"type": "string"},
        "confidence": {"type": "number"},
        "facts": {"type": "object"},
    },
    "required": ["certainty_basis", "confidence", "facts"],
}


def test_flattens_label_value_fact_list_and_derives_confidence_via_min():
    result = {
        "facts": [
            {"label": "courseCode", "value": "02340247", "source": "get_entity", "confidence": 1.0},
            {"label": "offeringPattern", "value": "irregular", "source": "extract_temporal_pattern", "confidence": 0.6},
        ]
    }

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["confidence"] == 0.6  # min across the two items
    assert set(normalized["facts"].keys()) == {"courseCode", "offeringPattern"}
    assert normalized["facts"]["courseCode"]["value"] == "02340247"


def test_flattens_items_keyed_by_their_key_field():
    # The Retrieval agent routinely emits [{key: <field name>, value: ...}];
    # a live-eval run showed a correct currentSemesterCode="2025-2" buried at
    # facts.fact_0 because "key" wasn't recognized as the label field, which
    # false-negatived the success-criteria check into an expensive replan.
    result = {
        "facts": [
            {"key": "currentSemesterCode", "value": "2025-2", "source": "get_current_semester", "confidence": 1.0},
        ]
    }

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert set(normalized["facts"].keys()) == {"currentSemesterCode"}
    assert normalized["facts"]["currentSemesterCode"]["value"] == "2025-2"


def test_flattens_fact_key_items_using_fact_text_as_the_dict_key():
    result = {
        "facts": [
            {"fact": "Prerequisites: 02340218 and 02340141.", "source": "get_course_profile", "confidence": "high"},
        ]
    }

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["confidence"] == 0.9  # "high" -> 0.9
    assert len(normalized["facts"]) == 1
    key = next(iter(normalized["facts"]))
    assert "Prerequisites" in key


def test_derives_confidence_from_nested_certainty_sub_object():
    result = {
        "facts": [
            {
                "label": "corequisites",
                "value": None,
                "certainty": {"basis": "wiki_derived", "confidence": 0.8},
            },
        ]
    }

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["confidence"] == 0.8
    assert normalized["certainty_basis"] == "wiki_derived"


def test_mixed_basis_across_items_falls_back_to_llm_interpretation():
    result = {
        "facts": [
            {"label": "a", "value": 1, "confidence": 0.9, "basis": "official_record"},
            {"label": "b", "value": 2, "confidence": 0.7, "basis": "predicted_pattern"},
        ]
    }

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["certainty_basis"] == "llm_interpretation"
    assert normalized["confidence"] == 0.7


def test_never_overwrites_certainty_the_model_already_provided():
    # If the model DID supply top-level certainty_basis/confidence, even
    # alongside a facts-list, those explicit values are never overwritten
    # by the derived aggregate.
    result = {
        "certainty_basis": "official_record",
        "confidence": 0.95,
        "facts": [{"label": "a", "value": 1, "confidence": 0.1}],
    }

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["certainty_basis"] == "official_record"
    assert normalized["confidence"] == 0.95


def test_facts_already_a_flat_object_is_left_unchanged():
    result = {"certainty_basis": "official_record", "confidence": 1.0, "facts": {"courseCode": "02340247"}}

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized == result


def test_non_dict_list_items_are_preserved_positionally():
    result = {"facts": ["a bare string fact", 42]}

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["facts"] == {"fact_0": "a bare string fact", "fact_1": 42}
    # The bare items carry no per-fact certainty to aggregate, so the required
    # certainty metadata is instead filled with its safe conservative default
    # (see _SAFE_REQUIRED_DEFAULTS) rather than left absent to cost an LLM
    # schema-repair call.
    assert normalized["confidence"] == 0.5
    assert normalized["certainty_basis"] == "llm_interpretation"


def test_absent_required_certainty_metadata_is_backfilled_not_repaired():
    # The dominant schema-repair trigger found via live-eval: the subagent
    # returns real facts but omits the required certainty_basis/confidence.
    # Backfilling conservative defaults makes the result validate with no LLM
    # round-trip.
    result = {"facts": {"courseCode": "02340247"}}

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["certainty_basis"] == "llm_interpretation"
    assert normalized["confidence"] == 0.5
    assert normalized["facts"] == {"courseCode": "02340247"}


def test_backfill_never_overwrites_metadata_the_model_provided():
    result = {"certainty_basis": "official_record", "confidence": 1.0, "facts": {"a": 1}}

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["certainty_basis"] == "official_record"
    assert normalized["confidence"] == 1.0


def test_backfill_skips_certainty_basis_when_default_is_not_a_legal_enum_value():
    # If the field constrains certainty_basis to an enum that excludes the
    # default, injecting the default would itself fail validation -- so the
    # field is left absent for the repair loop instead.
    schema = {
        "type": "object",
        "properties": {
            "certainty_basis": {"type": "string", "enum": ["official_record", "wiki_derived"]},
            "confidence": {"type": "number"},
            "facts": {"type": "object"},
        },
        "required": ["certainty_basis", "confidence", "facts"],
    }
    result = {"facts": {"a": 1}}

    normalized = normalize_structured_result(result, output_schema=schema)

    assert "certainty_basis" not in normalized  # not a legal enum value -> not injected
    assert normalized["confidence"] == 0.5  # confidence has no enum -> still backfilled


def test_absent_content_field_facts_is_not_backfilled():
    # Certainty metadata has safe defaults; a missing content field (facts)
    # is a real structural gap and must still surface, not be papered over.
    result = {"certainty_basis": "official_record", "confidence": 0.9}

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert "facts" not in normalized


def test_top_level_word_confidence_coerced_to_a_number():
    # A live-eval run found this alongside the facts-list mismatch: a
    # top-level "confidence" given as a word ("high") instead of a number.
    result = {"certainty_basis": "official_record", "confidence": "high", "facts": {"a": 1}}

    normalized = normalize_structured_result(result, output_schema=_RETRIEVAL_LIKE_SCHEMA)

    assert normalized["confidence"] == 0.9
