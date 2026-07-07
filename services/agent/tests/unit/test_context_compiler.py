"""Unit tests for the Phase 4 Context Compiler."""

from __future__ import annotations

import pytest

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import CapabilityNotFoundError, CapabilityRegistry
from app.agent.capabilities.schemas import CapabilityContextContract, CapabilityDescriptor
from app.agent.context_compiler import context_sections as sections
from app.agent.context_compiler.compiler import compile_context, compile_context_for_capability
from app.agent.context_compiler.reducers import sanitize_context_value
from app.agent.context_compiler.schemas import ContextCompilationRequest


def _capability(**context_kwargs: object) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        name="test_capability",
        type="tool",
        description="test",
        context=CapabilityContextContract(**context_kwargs),
    )


def _request(**overrides: object) -> ContextCompilationRequest:
    defaults: dict[str, object] = {
        "capability_name": "test_capability",
        "objective": "test objective",
        "user_message": "How many credits do I need?",
    }
    defaults.update(overrides)
    return ContextCompilationRequest(**defaults)


def test_compiler_includes_only_allowed_sections() -> None:
    capability = _capability(
        allowed_context_sections=[sections.USER_MESSAGE, sections.DETERMINISTIC_INTENT],
    )
    request = _request(deterministic_intent="course_question", conversation_summary="prior chat")
    compiled = compile_context(request, capability=capability)

    assert set(compiled.included_sections) == {sections.USER_MESSAGE, sections.DETERMINISTIC_INTENT}
    assert sections.CONVERSATION_SUMMARY not in compiled.context
    assert compiled.context[sections.USER_MESSAGE] == request.user_message
    assert compiled.context[sections.DETERMINISTIC_INTENT] == "course_question"


def test_compiler_omits_forbidden_sections_even_when_also_allowed() -> None:
    capability = _capability(
        allowed_context_sections=[sections.USER_MESSAGE, sections.WIKI_SNIPPETS],
        forbidden_context_sections=[sections.WIKI_SNIPPETS],
    )
    request = _request(wiki_snippets=[{"title": "Credits policy", "text": "..."}])
    compiled = compile_context(request, capability=capability)

    assert sections.WIKI_SNIPPETS not in compiled.context
    assert sections.WIKI_SNIPPETS in compiled.omitted_sections


def test_empty_allowed_sections_means_nothing_is_included() -> None:
    capability = _capability(allowed_context_sections=[])
    request = _request(deterministic_intent="course_question")
    compiled = compile_context(request, capability=capability)

    assert compiled.included_sections == []
    assert compiled.context == {}


def test_recent_messages_are_capped() -> None:
    capability = _capability(
        allowed_context_sections=[sections.RECENT_MESSAGES],
        max_recent_messages=2,
    )
    messages = [{"role": "user", "text": f"message {i}"} for i in range(10)]
    request = _request(recent_messages=messages)
    compiled = compile_context(request, capability=capability)

    included_messages = compiled.context[sections.RECENT_MESSAGES]
    assert len(included_messages) == 2
    # Keeps the most recent ones.
    assert included_messages[-1]["text"] == "message 9"


def test_wiki_snippets_are_capped() -> None:
    capability = _capability(
        allowed_context_sections=[sections.WIKI_SNIPPETS],
        max_wiki_snippets=3,
    )
    snippets = [{"title": f"doc-{i}"} for i in range(20)]
    request = _request(wiki_snippets=snippets)
    compiled = compile_context(request, capability=capability)

    assert len(compiled.context[sections.WIKI_SNIPPETS]) == 3


def test_attachment_metadata_included_but_contents_omitted_by_default() -> None:
    capability = _capability(
        allowed_context_sections=[sections.ATTACHMENT_METADATA],
        include_attachment_metadata=True,
    )
    request = _request(
        attachment_metadata=[
            {"type": "transcript_pdf", "filename": "transcript.pdf", "contentType": "application/pdf"}
        ],
        extra_context={"attachment_contents": "base64-blob-of-the-entire-pdf"},
    )
    compiled = compile_context(request, capability=capability)

    assert compiled.context[sections.ATTACHMENT_METADATA] == [
        {"type": "transcript_pdf", "filename": "transcript.pdf", "contentType": "application/pdf"}
    ]
    assert sections.EXTRA_CONTEXT not in compiled.context


def test_attachment_metadata_omitted_when_capability_disallows_it() -> None:
    capability = _capability(
        allowed_context_sections=[sections.ATTACHMENT_METADATA],
        include_attachment_metadata=False,
    )
    request = _request(attachment_metadata=[{"type": "transcript_pdf"}])
    compiled = compile_context(request, capability=capability)

    assert sections.ATTACHMENT_METADATA not in compiled.context
    assert sections.ATTACHMENT_METADATA in compiled.omitted_sections


def test_full_catalog_omitted_by_default() -> None:
    capability = _capability(allowed_context_sections=[sections.EXTRA_CONTEXT])
    request = _request(extra_context={"full_catalog": ["course"] * 500})
    compiled = compile_context(request, capability=capability)

    assert "full_catalog" not in compiled.context.get(sections.EXTRA_CONTEXT, {})
    assert any("full_catalog" in warning for warning in compiled.warnings)


def test_full_catalog_included_when_capability_explicitly_allows_it() -> None:
    capability = _capability(
        allowed_context_sections=[sections.EXTRA_CONTEXT],
        include_full_catalog=True,
    )
    request = _request(extra_context={"full_catalog": ["course-1", "course-2"]})
    compiled = compile_context(request, capability=capability)

    assert compiled.context[sections.EXTRA_CONTEXT]["full_catalog"] == ["course-1", "course-2"]
    assert not any("full_catalog" in warning for warning in compiled.warnings)


def test_full_transcript_rows_omitted_by_default() -> None:
    capability = _capability(allowed_context_sections=[sections.EXTRA_CONTEXT])
    request = _request(extra_context={"full_transcript_rows": [{"course": "234101"}] * 50})
    compiled = compile_context(request, capability=capability)

    assert "full_transcript_rows" not in compiled.context.get(sections.EXTRA_CONTEXT, {})
    assert any("full_transcript_rows" in warning for warning in compiled.warnings)


def test_raw_pdf_bytes_and_raw_mongo_document_are_always_forbidden() -> None:
    capability = _capability(
        allowed_context_sections=[sections.EXTRA_CONTEXT],
        include_full_catalog=True,
        include_full_transcript_rows=True,
        include_attachment_contents=True,
    )
    request = _request(
        extra_context={
            "raw_pdf_bytes": b"%PDF-1.4 ...",
            "raw_mongo_document": {"_id": "abc123", "field": "value"},
        }
    )
    compiled = compile_context(request, capability=capability)

    extra = compiled.context.get(sections.EXTRA_CONTEXT, {})
    assert "raw_pdf_bytes" not in extra
    assert "raw_mongo_document" not in extra
    assert any("raw_pdf_bytes" in warning for warning in compiled.warnings)
    assert any("raw_mongo_document" in warning for warning in compiled.warnings)


def test_sanitize_context_value_strips_binary_and_caps_oversized_collections() -> None:
    assert sanitize_context_value(b"binary-data") == "<omitted: binary data>"
    assert sanitize_context_value("x" * 10_000).endswith("…<truncated>")

    huge_list = list(range(200))
    sanitized_list = sanitize_context_value(huge_list)
    assert len(sanitized_list) <= 51  # capped items + one truncation marker
    assert any("more item(s) omitted" in str(item) for item in sanitized_list)


def test_nested_mongo_style_document_is_sanitized_within_allowed_sections() -> None:
    capability = _capability(allowed_context_sections=[sections.AGENT_CONTEXT_PACK_SUMMARY])
    request = _request(
        agent_context_pack_summary={
            "intent": "course_question",
            "validationStatus": "valid",
            # A deeply nested, oversized field that should never leak through raw.
            "rawNested": {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}},
        }
    )
    compiled = compile_context(request, capability=capability)

    summary = compiled.context[sections.AGENT_CONTEXT_PACK_SUMMARY]
    # `reduce_agent_context_pack_summary` only keeps a fixed whitelist of keys.
    assert "rawNested" not in summary
    assert summary["intent"] == "course_question"


def test_planner_context_includes_task_understanding() -> None:
    registry = build_default_capability_registry()
    request = ContextCompilationRequest(
        capability_name="planner_agent",
        objective="phase5_preview",
        user_message="Plan my next semester",
        task_understanding={"primaryIntent": "semester_plan_generation"},
    )
    compiled = compile_context_for_capability(request, registry=registry)

    assert sections.TASK_UNDERSTANDING in compiled.included_sections
    assert compiled.context[sections.TASK_UNDERSTANDING] == {
        "primaryIntent": "semester_plan_generation"
    }


def test_task_understanding_agent_context_excludes_large_academic_context() -> None:
    registry = build_default_capability_registry()
    request = ContextCompilationRequest(
        capability_name="task_understanding_agent",
        objective="understand_task",
        user_message="Can I graduate this semester?",
        agent_context_pack_summary={"intent": "graduation_progress_check"},
        wiki_snippets=[{"title": "policy"}],
    )
    compiled = compile_context_for_capability(request, registry=registry)

    assert sections.AGENT_CONTEXT_PACK_SUMMARY not in compiled.included_sections
    assert sections.WIKI_SNIPPETS not in compiled.included_sections
    assert sections.USER_MESSAGE in compiled.included_sections


def test_response_composer_context_includes_previous_results_not_raw_catalog() -> None:
    registry = build_default_capability_registry()
    request = ContextCompilationRequest(
        capability_name="response_composer_agent",
        objective="compose_final_reply",
        user_message="What's my progress?",
        previous_results={"graduationPercent": 72},
        extra_context={"full_catalog": ["course"] * 100},
    )
    compiled = compile_context_for_capability(request, registry=registry)

    assert compiled.context[sections.PREVIOUS_RESULTS] == {"graduationPercent": 72}
    extra = compiled.context.get(sections.EXTRA_CONTEXT, {})
    assert "full_catalog" not in extra
    assert any("full_catalog" in warning for warning in compiled.warnings)


def test_unknown_capability_raises_clear_error() -> None:
    registry = build_default_capability_registry()
    request = _request(capability_name="does_not_exist")
    with pytest.raises(CapabilityNotFoundError):
        compile_context_for_capability(request, registry=registry)


def test_disabled_capability_handling_is_deterministic() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDescriptor(
            name="disabled_capability",
            type="specialist_agent",
            description="not built yet",
            enabled=False,
            context=CapabilityContextContract(allowed_context_sections=[sections.USER_MESSAGE]),
        )
    )
    request = _request(capability_name="disabled_capability")

    first = compile_context_for_capability(request, registry=registry)
    second = compile_context_for_capability(request, registry=registry)

    assert first.model_dump() == second.model_dump()
    assert any("capability_disabled" in warning for warning in first.warnings)
    # A disabled capability still gets a (deterministic) compiled context —
    # compiling context is a data-shaping step, not an execution decision.
    assert sections.USER_MESSAGE in first.included_sections
