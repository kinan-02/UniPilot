"""Unit tests for `propose_action` (docs/agent/AGENT_VISION.md §5, primitive 9b).

Uses `FakeDatabase`/`fake_database_factory` (extended with `insert_one` for
this primitive specifically -- every other primitive so far was read-only).
"""

from __future__ import annotations

from datetime import datetime

from app.agent_core.tools.primitives.propose_action import ProposeActionInput, run_propose_action
from app.db.mongo import set_test_database
from app.repositories.agent_action_proposal_repository import AGENT_ACTION_PROPOSALS_COLLECTION


async def test_missing_action_type_fails_closed():
    result = await run_propose_action(ProposeActionInput(action_type="   ", payload={}))
    assert result.ok is False
    assert "action_type_required" in result.error


async def test_creates_a_pending_proposal(fake_database_factory):
    database = fake_database_factory({})
    set_test_database(database)

    result = await run_propose_action(
        ProposeActionInput(action_type="commit_transcript_import", payload={"userId": "u1", "rows": [1, 2, 3]})
    )
    assert result.ok is True
    assert result.data["actionType"] == "commit_transcript_import"
    assert result.data["payload"] == {"userId": "u1", "rows": [1, 2, 3]}
    assert result.data["status"] == "pending"
    assert isinstance(result.data["proposalId"], str) and result.data["proposalId"]
    # createdAt is a real, parseable ISO timestamp.
    datetime.fromisoformat(result.data["createdAt"])
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_payload_defaults_to_empty_dict(fake_database_factory):
    set_test_database(fake_database_factory({}))
    result = await run_propose_action(ProposeActionInput(action_type="save_semester_plan"))
    assert result.ok is True
    assert result.data["payload"] == {}


async def test_proposal_is_actually_persisted(fake_database_factory):
    database = fake_database_factory({})
    set_test_database(database)

    await run_propose_action(ProposeActionInput(action_type="save_semester_plan", payload={"planId": "p1"}))

    stored = database[AGENT_ACTION_PROPOSALS_COLLECTION]._docs
    assert len(stored) == 1
    assert stored[0]["actionType"] == "save_semester_plan"
    assert stored[0]["payload"] == {"planId": "p1"}
    assert stored[0]["status"] == "pending"


async def test_multiple_proposals_get_distinct_ids(fake_database_factory):
    set_test_database(fake_database_factory({}))
    first = await run_propose_action(ProposeActionInput(action_type="a", payload={}))
    second = await run_propose_action(ProposeActionInput(action_type="b", payload={}))
    assert first.data["proposalId"] != second.data["proposalId"]


async def test_action_type_is_not_validated_against_any_fixed_vocabulary(fake_database_factory):
    """Unlike every other vocabulary field in this codebase, propose_action
    never branches on action_type -- any non-empty string is accepted."""
    set_test_database(fake_database_factory({}))
    result = await run_propose_action(
        ProposeActionInput(action_type="a_brand_new_action_type_nobody_invented_yet", payload={})
    )
    assert result.ok is True
    assert result.data["actionType"] == "a_brand_new_action_type_nobody_invented_yet"


async def test_database_failure_fails_closed(monkeypatch):
    async def _raise():
        raise RuntimeError("connection lost")

    import app.agent_core.tools.primitives.propose_action as module

    monkeypatch.setattr(module, "get_database", _raise)
    result = await run_propose_action(ProposeActionInput(action_type="a", payload={}))
    assert result.ok is False
    assert "proposal_creation_failed" in result.error
