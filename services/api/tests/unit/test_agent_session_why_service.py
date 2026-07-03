"""Unit tests for agent session Why? service."""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.services.agent_session_why_service import (
    answer_agent_session_why,
    explain_agent_session_why_for_user,
)


def test_answer_agent_session_why_prefers_veto_turns() -> None:
    session = {
        "transcript": [
            {
                "agent_role": "planner",
                "action": "propose",
                "rationale": "Proposed 3 courses.",
                "references": [],
                "payload": {},
            },
            {
                "agent_role": "catalog_scout",
                "action": "veto",
                "rationale": "Missing prerequisite for 00940139.",
                "references": ["feasibility:missing_prereq"],
                "payload": {"violations": ["Missing prerequisite for 00940139."]},
            },
            {
                "agent_role": "arbiter",
                "action": "commit",
                "rationale": "Committed variant balanced.",
                "references": [],
                "payload": {
                    "course_ids": ["00140008"],
                    "utilityBreakdown": {"utility": 0.82},
                    "arbitration": {"chosen_variant": "balanced", "considered_variants": ["balanced"]},
                },
            },
        ],
        "finalDecision": {
            "course_ids": ["00140008"],
            "utilityBreakdown": {"utility": 0.82},
            "arbitration": {"chosen_variant": "balanced", "considered_variants": ["balanced"]},
        },
    }

    result = answer_agent_session_why(session, question="Why was the plan vetoed?")
    assert "catalog_scout" in result["answer"]
    assert result["citations"][0]["agentRole"] == "catalog_scout"
    assert "veto" in result["topics"]


def test_answer_agent_session_why_uses_reasoning_trace() -> None:
    session = {
        "transcript": [
            {
                "agent_role": "planner",
                "action": "propose",
                "rationale": "Planner proposal.",
                "references": [],
                "payload": {
                    "reasoningTrace": {
                        "kind": "planner_tool_loop",
                        "reasoning": "Chose light workload electives after graph lookup.",
                    }
                },
            }
        ],
        "finalDecision": {"course_ids": ["00140008"]},
    }

    result = answer_agent_session_why(session, question="Why these courses?")
    assert "graph lookup" in result["answer"]


def test_answer_agent_session_why_uses_progress_scout_trace() -> None:
    session = {
        "transcript": [
            {
                "agent_role": "progress_scout",
                "action": "critique",
                "rationale": "Soft progress pressure.",
                "references": [],
                "payload": {
                    "reasoningTrace": {
                        "kind": "progress_review",
                        "progressScore": 0.65,
                        "unlockCount": 1,
                        "critiques": [{"type": "slow_track", "message": "Does not unlock electives."}],
                    }
                },
            }
        ],
        "finalDecision": {"course_ids": ["00140008"]},
    }

    result = answer_agent_session_why(session, question="How does this affect graduation progress?")
    assert "progress_scout" in result["answer"]
    assert "Progress score" in result["answer"]
    assert "progress" in result["topics"]


@pytest.mark.asyncio
async def test_explain_agent_session_why_for_user_not_found(mongo_database) -> None:
    user_id = str(ObjectId())
    result = await explain_agent_session_why_for_user(
        mongo_database,
        user_id=user_id,
        session_id=str(ObjectId()),
        question="Why this plan?",
    )
    assert result["status"] == "not_found"
