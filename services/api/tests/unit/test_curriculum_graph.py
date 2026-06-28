"""Unit tests for curriculum graph builder and data quality."""

from __future__ import annotations

from app.curriculum.data_quality import (
    build_credits_display,
    parse_alternatives_from_text,
    parse_credits_range,
)
from app.curriculum.graph_builder import build_base_curriculum_graph
from app.curriculum.graph_overlay import (
    build_equivalence_groups,
    overlay_transcript_on_graph,
)


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


def test_parse_credits_range_returns_none_for_missing_raw():
    assert parse_credits_range(None) is None


def test_parse_credits_range_swaps_inverted_bounds():
    assert parse_credits_range("4.0-3.0") == {"min": 3.0, "max": 4.0}


def test_build_credits_display_without_any_credit_signal():
    display = build_credits_display(credits=None, credits_range=None, credits_hint=None)
    assert display["uncertain"] is True
    assert display["display"] == "—"


def test_prerequisite_sources_use_catalog_prerequisite_ids():
    from app.curriculum.graph_builder import _prerequisite_sources

    sources = _prerequisite_sources(
        {
            "courseNumber": "01040044",
            "prerequisites": ["665f2b0f2a3f7b2a1a9a7f01"],
        },
        None,
        {
            "665f2b0f2a3f7b2a1a9a7f01": {
                "_id": "665f2b0f2a3f7b2a1a9a7f01",
                "courseNumber": "01040042",
            }
        },
    )
    assert sources[0]["number"] == "01040042"
    assert sources[0]["requirementType"] == "hard"


def test_prerequisite_sources_include_corequisites_and_course_ref_text():
    from app.curriculum.graph_builder import _prerequisite_sources

    sources = _prerequisite_sources(
        {
            "courseNumber": "01040044",
            "corequisitesText": "01040031",
        },
        {"prerequisitesText": "01040042"},
        {},
    )
    numbers = {(item["number"], item["kind"]) for item in sources}
    assert ("01040042", "prerequisite") in numbers
    assert ("01040031", "corequisite") in numbers


def test_prerequisite_sources_skip_blank_numbers_and_duplicates():
    from app.curriculum.graph_builder import _prerequisite_sources

    sources = _prerequisite_sources(
        {"courseNumber": "01040044", "prerequisitesText": "01040042 01040042"},
        {"prerequisitesText": "   "},
        {},
    )
    assert len(sources) == 1


def test_build_base_graph_parses_credits_from_notes_and_hint_raw():
    graph = build_base_curriculum_graph(
        track_slug="track-data-information-engineering",
        program_code="009216-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
        semester_matrix_documents=[
            {
                "title": "Semester 1",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [
                    {
                        "courseNumber": "00940345",
                        "notes": ["3.5–4.0 credits"],
                        "creditsHintRaw": "3.0-3.5",
                    }
                ],
                "advisoryOnly": True,
            }
        ],
        pool_documents=[],
        catalog_courses=[],
    )
    node = graph["nodes"][0]
    assert node["credits"]["uncertain"] is True
    assert ("00960211", "00960221") in [
        tuple(group) for group in graph.get("crossTrackEquivalenceGroups", [])
    ]


def test_prerequisite_sources_deduplicate_duplicate_prerequisite_ids():
    from app.curriculum.graph_builder import _prerequisite_sources

    sources = _prerequisite_sources(
        {"prerequisites": ["665f2b0f2a3f7b2a1a9a7f01", "665f2b0f2a3f7b2a1a9a7f01"]},
        None,
        {
            "665f2b0f2a3f7b2a1a9a7f01": {
                "_id": "665f2b0f2a3f7b2a1a9a7f01",
                "courseNumber": "01040042",
            }
        },
    )
    assert len(sources) == 1


def test_build_base_graph_skips_invalid_matrix_course_reference():
    graph = build_base_curriculum_graph(
        track_slug="track-data-information-engineering",
        program_code="009216-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
        semester_matrix_documents=[
            {
                "title": "Semester 1",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [{"courseNumber": "invalid"}],
                "advisoryOnly": True,
            }
        ],
        pool_documents=[],
        catalog_courses=[],
    )
    assert graph["nodes"] == []


def test_build_base_graph_prefers_earlier_semester_for_duplicate_course(monkeypatch):
    original_sorted = sorted

    def reverse_semester_sort(items, key):
        return original_sorted(items, key=key, reverse=True)

    monkeypatch.setattr("builtins.sorted", reverse_semester_sort)
    graph = build_base_curriculum_graph(
        track_slug="track-data-information-engineering",
        program_code="009216-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
        semester_matrix_documents=[
            {
                "title": "Semester 1",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [{"courseNumber": "00940345"}],
                "advisoryOnly": True,
            },
            {
                "title": "Semester 2",
                "ruleExpression": {"type": "semester_matrix", "semester": 2},
                "courseReferences": [{"courseNumber": "00940345"}],
                "advisoryOnly": True,
            },
        ],
        pool_documents=[],
        catalog_courses=[{"_id": "665f2b0f2a3f7b2a1a9a7f01", "courseNumber": "00940345", "credits": 4.0}],
    )
    assert graph["nodes"][0]["semester"] == 1


def test_prerequisite_sources_skip_missing_prerequisite_numbers():
    from app.curriculum.graph_builder import _prerequisite_sources

    sources = _prerequisite_sources(
        {"prerequisites": ["665f2b0f2a3f7b2a1a9a7f01"]},
        None,
        {"665f2b0f2a3f7b2a1a9a7f01": {"_id": "665f2b0f2a3f7b2a1a9a7f01"}},
    )
    assert sources == []


def test_prerequisite_sources_deduplicate_hard_and_textual_prerequisites():
    from app.curriculum.graph_builder import _prerequisite_sources

    sources = _prerequisite_sources(
        {
            "courseNumber": "01040044",
            "prerequisites": ["665f2b0f2a3f7b2a1a9a7f01"],
            "prerequisitesText": "01040042",
        },
        None,
        {
            "665f2b0f2a3f7b2a1a9a7f01": {
                "_id": "665f2b0f2a3f7b2a1a9a7f01",
                "courseNumber": "01040042",
            }
        },
    )
    assert len(sources) == 1
    assert sources[0]["number"] == "01040042"


def test_build_base_graph_skips_invalid_course_numbers_and_marks_external_prerequisites():
    graph = build_base_curriculum_graph(
        track_slug="track-data-information-engineering",
        program_code="009216-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
        semester_matrix_documents=[
            {
                "title": "Semester 2",
                "ruleExpression": {"type": "semester_matrix", "semester": 2},
                "courseReferences": [{"courseNumber": "00940345"}],
                "advisoryOnly": True,
            }
        ],
        pool_documents=[],
        catalog_courses=[
            {
                "_id": "665f2b0f2a3f7b2a1a9a7f01",
                "courseNumber": "00940345",
                "title": "Discrete",
                "credits": 4.0,
                "prerequisitesText": "01040042",
            }
        ],
    )
    assert len(graph["nodes"]) == 1
    external = [edge for edge in graph["edges"] if edge["kind"] == "external_prerequisite"]
    assert external
    assert external[0]["from"] == "01040042"


def test_course_number_helper_returns_none_without_number():
    from app.curriculum.graph_builder import _course_number

    assert _course_number({"title": "No number"}) is None


def test_build_base_graph_uses_credits_hint_raw_when_notes_missing():
    graph = build_base_curriculum_graph(
        track_slug="track-data-information-engineering",
        program_code="009216-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
        semester_matrix_documents=[
            {
                "title": "Semester 1",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [
                    {
                        "courseNumber": "00940345",
                        "creditsHintRaw": "3.0-3.5",
                    }
                ],
                "advisoryOnly": True,
            }
        ],
        pool_documents=[],
        catalog_courses=[],
    )
    assert graph["nodes"][0]["credits"]["uncertain"] is True


def test_overlay_marks_failed_and_verify_statuses():
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
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": False},
            },
            {
                "nodeId": "C",
                "courseNumber": "C",
                "semester": 3,
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": True},
            },
        ],
        "edges": [{"from": "A", "to": "B", "kind": "prerequisite"}],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(
        base,
        [
            {"courseNumber": "A", "grade": 95},
            {"courseNumber": "B", "grade": 45},
        ],
    )
    by_number = {node["courseNumber"]: node for node in graph["nodes"]}
    assert by_number["A"]["status"] == "completed"
    assert by_number["B"]["status"] == "failed"
    assert by_number["C"]["status"] == "verify_with_registrar"


def test_in_progress_numbers_helper():
    from app.curriculum.graph_overlay import _in_progress_numbers

    numbers = _in_progress_numbers(
        [{"courseNumber": "00940345", "inProgress": True, "grade": 80}]
    )
    assert numbers == {"00940345"}


def test_overlay_marks_available_and_highlights_bottleneck_edge():
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
                "prerequisiteNumbers": ["A", "C"],
                "dataQuality": {"verifyWithRegistrar": False},
            },
        ],
        "edges": [{"from": "A", "to": "B", "kind": "prerequisite"}],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(base, [{"courseNumber": "A", "grade": 90}])
    by_number = {node["courseNumber"]: node for node in graph["nodes"]}
    assert by_number["B"]["status"] == "blocked"
    assert graph["edges"][0]["highlight"] == "bottleneck"


def test_overlay_marks_in_progress_status(monkeypatch):
    import app.curriculum.graph_overlay as graph_overlay

    monkeypatch.setattr(graph_overlay, "_completed_numbers", lambda _records: set())
    monkeypatch.setattr(graph_overlay, "_failed_numbers", lambda _records: set())
    base = {
        "nodes": [
            {
                "nodeId": "C",
                "courseNumber": "C",
                "semester": 1,
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": False},
            }
        ],
        "edges": [],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(
        base,
        [{"courseNumber": "C", "inProgress": True}],
    )
    assert graph["nodes"][0]["status"] == "in_progress"


def test_overlay_marks_verify_with_registrar_when_flag_set():
    base = {
        "nodes": [
            {
                "nodeId": "C",
                "courseNumber": "C",
                "semester": 1,
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": True},
            }
        ],
        "edges": [],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(base, [])
    assert graph["nodes"][0]["status"] == "verify_with_registrar"


def test_build_equivalence_groups_merges_primary_and_alternatives():
    groups = build_equivalence_groups(
        [
            {
                "courseNumber": "1040065",
                "alternatives": ["1040016"],
            }
        ]
    )
    equivalence = groups.get("1040065") or groups.get("01040065") or set()
    assert "1040016" in equivalence or "01040016" in equivalence


def test_build_equivalence_groups_skips_nodes_without_primary_number():
    groups = build_equivalence_groups([{"courseNumber": "", "alternatives": ["1040016"]}])
    assert "1040016" not in groups
    assert "01040016" not in groups


def test_completed_via_alternative_returns_equivalent_candidate():
    from app.curriculum.graph_overlay import _completed_via_alternative

    groups = build_equivalence_groups(
        [{"courseNumber": "1040065", "alternatives": ["1040016"]}],
    )
    candidate = _completed_via_alternative(
        primary="1040065",
        completed={"01040016"},
        groups=groups,
    )
    assert candidate == "01040016"


def test_overlay_skips_bottleneck_highlight_when_edge_nodes_missing():
    base = {
        "nodes": [
            {
                "nodeId": "known-target",
                "courseNumber": "B",
                "semester": 2,
                "prerequisiteNumbers": ["A"],
                "dataQuality": {"verifyWithRegistrar": False},
            }
        ],
        "edges": [{"from": "missing-source", "to": "known-target", "kind": "prerequisite"}],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(base, [])
    assert graph["edges"][0].get("highlight") != "bottleneck"


def test_overlay_marks_completed_when_parallel_alternative_passed():
    base = {
        "nodes": [
            {
                "nodeId": "1040065",
                "courseNumber": "1040065",
                "semester": 1,
                "alternatives": ["1040016"],
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": False},
            }
        ],
        "edges": [],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(
        base,
        [{"courseNumber": "01040016", "grade": 85}],
    )
    node = graph["nodes"][0]
    assert node["status"] == "completed"
    assert node["satisfiedViaAlternative"] == "01040016"


def test_overlay_unblocks_dependent_when_prereq_satisfied_via_alternative():
    base = {
        "nodes": [
            {
                "nodeId": "1040065",
                "courseNumber": "1040065",
                "semester": 1,
                "alternatives": ["1040016"],
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": False},
            },
            {
                "nodeId": "1040311",
                "courseNumber": "1040311",
                "semester": 2,
                "alternatives": [],
                "prerequisiteNumbers": ["1040065"],
                "dataQuality": {"verifyWithRegistrar": False},
            },
        ],
        "edges": [{"from": "1040065", "to": "1040311", "kind": "prerequisite"}],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(
        base,
        [{"courseNumber": "1040016", "grade": 90}],
    )
    by_number = {node["courseNumber"]: node for node in graph["nodes"]}
    assert by_number["1040065"]["status"] == "completed"
    assert by_number["1040311"]["status"] == "available"
    assert by_number["1040311"]["missingPrerequisites"] == []


def test_overlay_keeps_failed_when_primary_failed_and_no_alternative_passed():
    base = {
        "nodes": [
            {
                "nodeId": "1040065",
                "courseNumber": "1040065",
                "semester": 1,
                "alternatives": ["1040016"],
                "prerequisiteNumbers": [],
                "dataQuality": {"verifyWithRegistrar": False},
            }
        ],
        "edges": [],
        "bottlenecks": [],
    }
    graph = overlay_transcript_on_graph(
        base,
        [{"courseNumber": "1040065", "grade": 40}],
    )
    assert graph["nodes"][0]["status"] == "failed"
    assert "satisfiedViaAlternative" not in graph["nodes"][0]
