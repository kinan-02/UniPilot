"""Named context sections the Context Compiler can include/omit (Phase 4).

These names are the vocabulary shared between `CapabilityContextContract`
(`allowed_context_sections`/`forbidden_context_sections`) and
`ContextCompilationRequest`/`compiler.py`. Keeping them as string constants
(not just inline literals) means a typo in a capability contract or a
compiler reducer is a clear `NameError`/lookup miss rather than a silently
ignored section name.
"""

from __future__ import annotations

from typing import Final

USER_MESSAGE: Final[str] = "user_message"
TASK_UNDERSTANDING: Final[str] = "task_understanding"
DETERMINISTIC_INTENT: Final[str] = "deterministic_intent"
DETERMINISTIC_ENTITIES: Final[str] = "deterministic_entities"
CONVERSATION_SUMMARY: Final[str] = "conversation_summary"
RECENT_MESSAGES: Final[str] = "recent_messages"
CONVERSATION_ENTITIES: Final[str] = "conversation_entities"
CONVERSATION_ASSUMPTIONS: Final[str] = "conversation_assumptions"
PROFILE_SUMMARY: Final[str] = "profile_summary"
ATTACHMENT_METADATA: Final[str] = "attachment_metadata"
AGENT_CONTEXT_PACK_SUMMARY: Final[str] = "agent_context_pack_summary"
WIKI_SNIPPETS: Final[str] = "wiki_snippets"
PREVIOUS_RESULTS: Final[str] = "previous_results"
EXTRA_CONTEXT: Final[str] = "extra_context"

ALL_CONTEXT_SECTIONS: Final[frozenset[str]] = frozenset(
    {
        USER_MESSAGE,
        TASK_UNDERSTANDING,
        DETERMINISTIC_INTENT,
        DETERMINISTIC_ENTITIES,
        CONVERSATION_SUMMARY,
        RECENT_MESSAGES,
        CONVERSATION_ENTITIES,
        CONVERSATION_ASSUMPTIONS,
        PROFILE_SUMMARY,
        ATTACHMENT_METADATA,
        AGENT_CONTEXT_PACK_SUMMARY,
        WIKI_SNIPPETS,
        PREVIOUS_RESULTS,
        EXTRA_CONTEXT,
    }
)

# Large/unsafe payload keys that must never reach a capability unless it
# explicitly opts in via its `CapabilityContextContract` (e.g.
# `include_full_catalog=True`). These are checked against
# `ContextCompilationRequest.extra_context` keys regardless of the
# capability's `allowed_context_sections` list — see `compiler.py`.
FORBIDDEN_BY_DEFAULT_CONTEXT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "full_catalog",
        "full_transcript_rows",
        "attachment_contents",
        "raw_pdf_bytes",
        "raw_mongo_document",
    }
)
