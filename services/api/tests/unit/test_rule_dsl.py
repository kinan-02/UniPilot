"""Unit tests for elective bucket rule DSL."""

from __future__ import annotations

from app.curriculum.rule_dsl import (
    parse_rule_expression,
    resolve_progress_display,
    summarize_elective_bucket,
)
from app.services.graduation_requirement_links import credit_bucket_id_for_pool


def test_parse_rule_expression_choose_chain():
    parsed = parse_rule_expression(
        {
            "type": "course_pool",
            "operator": "choose_chain",
            "chooseCount": 3,
            "chain": "ml",
        }
    )
    assert parsed["type"] == "course_pool"
    assert parsed["operator"] == "choose_chain"
    assert parsed["chooseCount"] == 3
    assert parsed["chain"] == "ml"
    assert parsed["isHardRule"] is False


def test_parse_rule_expression_choose_n():
    parsed = parse_rule_expression(
        {"type": "course_pool", "operator": "choose_n", "chooseCount": 1, "chain": "statistics"}
    )
    assert parsed["operator"] == "choose_n"
    assert parsed["chooseCount"] == 1


def test_summarize_elective_bucket_includes_courses_and_link():
    pool_doc = {
        "requirementGroupId": "009216-1-000:elective-ds-pool",
        "title": "Data science elective pool",
        "ruleExpression": {
            "type": "course_pool",
            "operator": "choose_credits",
            "allowedPrefixes": ["009"],
        },
        "courseReferences": [
            {"courseNumber": "00940411", "titleHint": "Intro to data science", "creditsHint": 3.5},
        ],
        "advisoryOnly": True,
    }
    summary = summarize_elective_bucket(
        pool_doc,
        program_code="009216-1-000",
        courses_by_number={
            "00940411": {
                "courseNumber": "00940411",
                "title": "Intro to Data Science",
                "credits": 3.5,
            }
        },
        linked_credit_bucket_id=credit_bucket_id_for_pool(
            program_code="009216-1-000",
            pool_document=pool_doc,
        ),
    )

    assert summary["explorerReady"] is True
    assert summary["linkedCreditBucketId"] == "009216-1-000:elective-ds"
    assert summary["allowedPrefixes"] == ["009"]
    assert summary["courses"][0]["title"] == "Intro to Data Science"
    assert summary["courses"][0]["credits"] == 3.5
    assert summary["rule"]["operator"] == "choose_credits"


def test_credit_bucket_id_for_pool_uses_explicit_link():
    pool_doc = {
        "requirementGroupId": "009118-1-000:is-focus-chain-ml",
        "linkedCreditBucketId": "009118-1-000:elective-faculty",
    }
    assert credit_bucket_id_for_pool(
        program_code="009118-1-000",
        pool_document=pool_doc,
    ) == "009118-1-000:elective-faculty"


def test_resolve_progress_display_chain_vs_shared_bucket():
    chain_doc = {
        "requirementGroupId": "009118-1-000:is-behavior-science-chain",
        "ruleExpression": {"type": "course_pool", "operator": "choose_n", "chooseCount": 1},
    }
    additional_doc = {
        "requirementGroupId": "009118-1-000:is-additional-faculty-electives",
        "ruleExpression": {
            "type": "course_pool",
            "operator": "min_credits",
            "allowedPrefixes": ["0094"],
        },
    }
    ds_doc = {
        "requirementGroupId": "009216-1-000:elective-ds-pool",
        "ruleExpression": {"type": "course_pool", "operator": "min_credits"},
    }

    assert resolve_progress_display(chain_doc, program_code="009118-1-000") == "chain_steps"
    assert resolve_progress_display(additional_doc, program_code="009118-1-000") == "shared_bucket_credits"
    assert resolve_progress_display(ds_doc, program_code="009216-1-000") == "dedicated_bucket_credits"
