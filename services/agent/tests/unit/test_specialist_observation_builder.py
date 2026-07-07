"""Unit tests for `app.agent.specialists.tools.observation_builder` (Phase 12).

Pure, deterministic, no I/O, no LLM calls -- every test constructs an
in-memory `AgentContextPack` (or a lightweight duck-typed stand-in) and
inspects the resulting `SpecialistObservationBundle`.
"""

from __future__ import annotations

from app.agent.schemas import AgentContextPack, WikiContextSnippet
from app.agent.specialists.tools.observation_builder import build_specialist_observations
from app.agent.specialists.tools.registry import build_default_observation_registry
from app.agent.specialists.tools.schemas import SpecialistObservationRequest


def _pack(**overrides) -> AgentContextPack:
    defaults = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


def _request(**overrides) -> SpecialistObservationRequest:
    defaults = dict(
        specialist_agent_name="graduation_progress_agent",
        subtask_id="s1",
        objective="check progress",
        user_message="What am I missing to graduate?",
    )
    defaults.update(overrides)
    return SpecialistObservationRequest(**defaults)


def _by_name(bundle, name):
    return next(obs for obs in bundle.observations if obs.name == name)


# ---------------------------------------------------------------------------
# 1. Builds profile_summary from compiled context (no pack available).
# ---------------------------------------------------------------------------


def test_builds_profile_summary_from_compiled_context() -> None:
    request = _request(
        compiled_context={"profile_summary": {"degreeProgram": "BSc", "track": "data-eng", "catalogYear": 2024}}
    )

    bundle = build_specialist_observations(request, agent_context_pack=None)

    observation = _by_name(bundle, "profile_summary")
    assert observation.status == "available"
    assert observation.source == "compiled_context"
    assert observation.summary["degreeProgram"] == "BSc"
    assert observation.summary["track"] == "data-eng"


def test_profile_summary_prefers_agent_context_pack_over_compiled_context() -> None:
    pack = _pack(user_context={"profile": {"degreeProgram": "MSc"}})
    request = _request(compiled_context={"profile_summary": {"degreeProgram": "BSc"}})

    bundle = build_specialist_observations(request, agent_context_pack=pack)

    observation = _by_name(bundle, "profile_summary")
    assert observation.source == "agent_context_pack"
    assert observation.summary["degreeProgram"] == "MSc"


# ---------------------------------------------------------------------------
# 2. Builds completed_courses_summary from context summary.
# ---------------------------------------------------------------------------


def test_builds_completed_courses_summary_from_agent_context_pack() -> None:
    pack = _pack(
        user_context={
            "completedCourses": ["234123", "104031"],
            "completedCourseIds": ["a1", "a2"],
            "dataQuality": {"ok": True},
        }
    )
    request = _request()

    bundle = build_specialist_observations(request, agent_context_pack=pack)

    observation = _by_name(bundle, "completed_courses_summary")
    assert observation.status == "available"
    assert observation.summary["completedCourseCount"] == 2
    assert observation.summary["sampleCourseNumbers"] == ["234123", "104031"]
    assert observation.summary["dataQuality"] == {"ok": True}


# ---------------------------------------------------------------------------
# 3. Builds graduation_audit_summary when available.
# ---------------------------------------------------------------------------


def test_builds_graduation_audit_summary_from_academic_context() -> None:
    pack = _pack(
        academic_context={
            "graduationAudit": {
                "creditsEarned": 80.0,
                "creditsRequired": 120.0,
                "creditsRemaining": 40.0,
                "isEligibleForGraduation": False,
            }
        }
    )
    request = _request()

    bundle = build_specialist_observations(request, agent_context_pack=pack)

    observation = _by_name(bundle, "graduation_audit_summary")
    assert observation.status == "available"
    assert observation.source == "deterministic_summary"
    assert observation.summary["creditsRemaining"] == 40.0
    assert observation.summary["isEligibleForGraduation"] is False


# ---------------------------------------------------------------------------
# 4. Builds course_catalog_summary when available.
# ---------------------------------------------------------------------------


def test_builds_course_catalog_summary_from_academic_context() -> None:
    pack = _pack(
        academic_context={"course": {"id": "c1", "courseNumber": "234123", "title": "Intro to CS", "credits": 5.0}}
    )
    request = _request(specialist_agent_name="course_catalog_agent")

    bundle = build_specialist_observations(request, agent_context_pack=pack)

    observation = _by_name(bundle, "course_catalog_summary")
    assert observation.status == "available"
    assert observation.summary == {"id": "c1", "courseNumber": "234123", "title": "Intro to CS", "credits": 5.0}


# ---------------------------------------------------------------------------
# 5. Builds wiki_snippet_summary with capped snippets.
# ---------------------------------------------------------------------------


def test_builds_wiki_snippet_summary_capped() -> None:
    snippets = [
        WikiContextSnippet(page_title=f"Page {i}", content="x" * 500, score=0.9 - i * 0.1) for i in range(10)
    ]
    pack = _pack(retrieved_wiki_context=snippets)
    request = _request(specialist_agent_name="course_catalog_agent")

    bundle = build_specialist_observations(request, agent_context_pack=pack)

    observation = _by_name(bundle, "wiki_snippet_summary")
    assert observation.status == "available"
    assert observation.summary["snippetCount"] == 10
    # descriptor max_summary_items for wiki_snippet_summary is 5.
    assert len(observation.summary["sampleSnippets"]) == 5
    for sample in observation.summary["sampleSnippets"]:
        assert len(sample["preview"]) <= 221  # 220 chars + ellipsis


# ---------------------------------------------------------------------------
# 6. Returns missing observation when source unavailable.
# ---------------------------------------------------------------------------


def test_returns_missing_status_when_source_unavailable() -> None:
    request = _request()

    bundle = build_specialist_observations(request, agent_context_pack=None)

    observation = _by_name(bundle, "graduation_audit_summary")
    assert observation.status == "missing"
    assert observation.summary == {}
    assert "observation_source_unavailable" in observation.warnings


# ---------------------------------------------------------------------------
# 7. max_observations is enforced.
# ---------------------------------------------------------------------------


def test_max_observations_is_enforced() -> None:
    request = _request(specialist_agent_name="course_catalog_agent", max_observations=2)

    bundle = build_specialist_observations(request, agent_context_pack=None)

    assert len(bundle.observations) == 2
    assert len(bundle.omitted_observations) > 0
    assert any(w.startswith("observation_omitted_max_count_reached:") for w in bundle.warnings)


def test_zero_max_observations_builds_nothing() -> None:
    request = _request(max_observations=0)

    bundle = build_specialist_observations(request, agent_context_pack=None)

    assert bundle.observations == []


# ---------------------------------------------------------------------------
# 8. Unsupported/not-allowed observation is omitted with a warning.
# ---------------------------------------------------------------------------


def test_observation_not_allowed_for_specialist_is_omitted_with_warning() -> None:
    request = _request(
        specialist_agent_name="graduation_progress_agent",
        allowed_observations=["course_catalog_summary"],
    )

    bundle = build_specialist_observations(request, agent_context_pack=None)

    assert bundle.observations == []
    assert "course_catalog_summary" in bundle.omitted_observations
    assert "observation_not_allowed_for_specialist:course_catalog_summary" in bundle.warnings


def test_unknown_observation_name_is_omitted_with_warning() -> None:
    registry = build_default_observation_registry()
    request = _request(allowed_observations=["not_a_real_observation"])

    bundle = build_specialist_observations(request, agent_context_pack=None, registry=registry)

    assert bundle.observations == []
    assert "not_a_real_observation" in bundle.omitted_observations


# ---------------------------------------------------------------------------
# 9. Dependency outputs can contribute observations.
# ---------------------------------------------------------------------------


def test_dependency_outputs_contribute_graduation_audit_summary() -> None:
    request = _request(
        dependency_outputs={
            "check_audit": {"creditsEarned": 90.0, "creditsRequired": 120.0, "status": "in_progress"}
        }
    )

    bundle = build_specialist_observations(request, agent_context_pack=None)

    observation = _by_name(bundle, "graduation_audit_summary")
    assert observation.status == "available"
    assert observation.summary["creditsEarned"] == 90.0


# ---------------------------------------------------------------------------
# 10. Builder never raises on malformed context.
# ---------------------------------------------------------------------------


def test_builder_never_raises_on_malformed_agent_context_pack() -> None:
    class _Hostile:
        def __getattr__(self, _name):
            raise RuntimeError("boom")

    request = _request(specialist_agent_name="course_catalog_agent")

    bundle = build_specialist_observations(request, agent_context_pack=_Hostile())

    # Every observation degrades to "missing" (or, at worst, "failed") --
    # the call itself must not raise.
    assert len(bundle.observations) > 0
    assert all(obs.status in ("missing", "failed") for obs in bundle.observations)


def test_builder_never_raises_on_malformed_compiled_context() -> None:
    request = _request(compiled_context={"profile_summary": "not-a-dict", "wiki_snippets": "not-a-list"})

    bundle = build_specialist_observations(request, agent_context_pack=None)

    assert bundle is not None


def test_builder_never_raises_on_malformed_dependency_outputs() -> None:
    request = _request(dependency_outputs={"x": "not-a-dict", "y": ["also", "not", "a", "dict"]})

    bundle = build_specialist_observations(request, agent_context_pack=None)

    assert bundle is not None
    observation = _by_name(bundle, "graduation_audit_summary")
    assert observation.status == "missing"


# ---------------------------------------------------------------------------
# Extra: bundle-level invariants.
# ---------------------------------------------------------------------------


def test_bundle_never_carries_a_summary_with_forbidden_keys() -> None:
    pack = _pack(
        academic_context={
            "course": {"courseNumber": "234123", "title": "Intro"},
        }
    )
    request = _request(specialist_agent_name="course_catalog_agent")

    bundle = build_specialist_observations(request, agent_context_pack=pack)

    dumped = str(bundle.model_dump())
    for forbidden in ("chain_of_thought", "raw_context", "proposed_action_payload", "full_catalog"):
        assert forbidden not in dumped


def test_observations_are_returned_in_registry_order() -> None:
    request = _request(specialist_agent_name="course_catalog_agent")

    bundle = build_specialist_observations(request, agent_context_pack=None)

    registry = build_default_observation_registry()
    allowed_order = registry.allowed_observations_for_specialist("course_catalog_agent")
    built_names = [obs.name for obs in bundle.observations]
    assert built_names == allowed_order[: len(built_names)]
