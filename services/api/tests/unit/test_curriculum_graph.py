"""Unit tests for curriculum graph builder and data quality."""

from __future__ import annotations

from app.curriculum.data_quality import (
    build_credits_display,
    parse_alternatives_from_text,
    parse_credits_range,
)
from app.curriculum.graph_builder import build_base_curriculum_graph
from app.curriculum.graph_overlay import overlay_transcript_on_graph


def test_parse_credits_range_detects_en_dash():
    assert parse_credits_range("3.5–4.0") == {"min": 3.5, "max": 4.0}


def test_parse_alternatives_from_notes():
    assert parse_alternatives_from_text("Alt: 1040016 (if retake needed)") == ["1040016"]


def test_build_credits_display_marks_range_uncertain():
    display = build_credits_display(
        credits=None,
        credits_range={"min": 3.5, "max": 4.0},
        credits_hint=3.75,
    )
    assert display["uncertain"] is True
    assert display["value"] is None
    assert "3.5" in display["display"]


def test_prerequisite_sources_resolve_from_prerequisites_text():
    from app.curriculum.graph_builder import _prerequisite_sources

    sources = _prerequisite_sources(
        {
            "_id": "665f2b0f2a3f7b2a1a9a7f01",
            "courseNumber": "01040044",
            "prerequisitesText": "1040042 חשבון דיפרנציאלי 1",
        },
        None,
        {},
    )
    assert sources == [
        {
            "number": "01040042",
            "requirementType": "catalog_text",
            "kind": "prerequisite",
        }
    ]


def test_build_base_graph_emits_prerequisite_edges_from_text():
    graph = build_base_curriculum_graph(
        track_slug="track-information-systems-engineering",
        program_code="009118-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
        semester_matrix_documents=[
            {
                "title": "Semester 1",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [{"courseNumber": "01040042", "titleHint": "Calc 1"}],
                "advisoryOnly": True,
            },
            {
                "title": "Semester 2",
                "ruleExpression": {"type": "semester_matrix", "semester": 2},
                "courseReferences": [{"courseNumber": "01040044", "titleHint": "Calc 2"}],
                "advisoryOnly": True,
            },
        ],
        pool_documents=[],
        catalog_courses=[
            {
                "_id": "665f2b0f2a3f7b2a1a9a7f01",
                "courseNumber": "01040042",
                "title": "Calc 1",
                "credits": 5.0,
                "prerequisites": [],
            },
            {
                "_id": "665f2b0f2a3f7b2a1a9a7f02",
                "courseNumber": "01040044",
                "title": "Calc 2",
                "credits": 5.0,
                "prerequisitesText": "01040042",
            },
        ],
    )

    internal_edges = [edge for edge in graph["edges"] if edge["kind"] == "prerequisite"]
    assert {
        "from": "01040042",
        "to": "01040044",
        "requirementType": "catalog_text",
    } in [
        {
            "from": edge["from"],
            "to": edge["to"],
            "requirementType": edge["requirementType"],
        }
        for edge in internal_edges
    ]


def test_build_base_graph_includes_semester_lanes_and_alternatives():
    graph = build_base_curriculum_graph(
        track_slug="track-information-systems-engineering",
        program_code="009118-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
        semester_matrix_documents=[
            {
                "title": "Semester 1",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [
                    {
                        "courseNumber": "1040065",
                        "titleHint": "Algebra",
                        "creditsHint": 5.0,
                        "notes": ["Alt: 1040016"],
                        "alternatives": ["1040016"],
                    }
                ],
                "advisoryOnly": True,
            }
        ],
        pool_documents=[
            {
                "requirementGroupId": "009118-1-000:is-focus-chain-ml",
                "title": "Focus chain",
                "ruleExpression": {"type": "course_pool", "operator": "choose_chain"},
                "courseReferences": [],
                "advisoryOnly": True,
            }
        ],
        catalog_courses=[
            {
                "_id": "665f2b0f2a3f7b2a1a9a7f01",
                "courseNumber": "1040065",
                "title": "Algebra 1",
                "credits": 5.0,
                "prerequisites": [],
            }
        ],
    )

    assert len(graph["semesterLanes"]) == 1
    node = graph["nodes"][0]
    assert node["alternatives"] == ["1040016"]
    assert node["dataQuality"]["hasAlternatives"] is True
    assert graph["electiveBuckets"][0]["explorerReady"] is True
    assert graph["electiveBuckets"][0]["rule"]["operator"] == "choose_chain"
    assert graph["advisories"][0]["code"] == "semester_matrix_planning_only"


def test_overlay_marks_blocked_when_prereq_missing():
    base = {
        "nodes": [
            {
                "nodeId": "A",
                "courseNumber": "A",
                "semester": 1,
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": False},
            },
            {
                "nodeId": "B",
                "courseNumber": "B",
                "semester": 2,
                "prerequisiteNumbers": ["A"],
                "dataQuality": {"verifyWithRegistrar": False},
            },
        ],
        "edges": [{"from": "A", "to": "B", "kind": "prerequisite"}],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(base, [])
    by_number = {node["courseNumber"]: node for node in graph["nodes"]}
    assert by_number["B"]["status"] == "blocked"
    assert graph["bottlenecks"][0]["courseNumber"] == "B"
