"""Structured focus-chain layouts mirrored from web chainRequirementSteps.ts."""

from __future__ import annotations

from typing import Any

DNE_STARRED_COURSE_NUMBERS: tuple[str, ...] = (
    "0960222",
    "0960231",
    "0960235",
    "0960262",
    "0960324",
    "0960693",
    "0970135",
    "0970200",
    "0970215",
    "0970216",
    "0970222",
    "0970247",
    "0970248",
    "0970272",
    "0970400",
)

FLEXIBLE_CHAIN_SUFFIXES: frozenset[str] = frozenset(
    {
        "ie-focus-chain-data-systems",
        "ie-focus-chain-or-game-theory",
        "ie-focus-chain-statistics",
        "ie-focus-chain-economics",
        "ie-focus-chain-behavior-management",
    }
)

_POOL_CHAIN_LAYOUTS: dict[str, dict[str, Any]] = {
    "is-behavior-science-chain": {
        "type": "steps",
        "steps": [
            {
                "id": "behavior",
                "kind": "choose_one",
                "courseNumbers": ["0960600", "0960620"],
            },
        ],
    },
    "is-focus-chain-performance": {
        "type": "steps",
        "steps": [
            {"id": "p1", "kind": "required", "courseNumbers": ["0960327"]},
            {
                "id": "p2",
                "kind": "required",
                "courseNumbers": ["0960324", "0980413"],
            },
            {
                "id": "p3",
                "kind": "choose_one",
                "courseNumbers": [
                    "0960311",
                    "0960335",
                    "0960351",
                    "0970135",
                    "0970280",
                    "0970325",
                    "0970334",
                ],
            },
        ],
    },
    "is-focus-chain-ml": {
        "type": "steps",
        "steps": [
            {"id": "p1", "kind": "required", "courseNumbers": ["0970209"]},
            {
                "id": "p2",
                "kind": "choose_one",
                "courseNumbers": ["0960212", "0960327", "0970414"],
            },
            {
                "id": "p3",
                "kind": "choose_one",
                "courseNumbers": list(DNE_STARRED_COURSE_NUMBERS),
            },
        ],
    },
    "is-focus-chain-game-theory": {
        "type": "steps",
        "steps": [
            {
                "id": "p1",
                "kind": "choose_one",
                "courseNumbers": ["0960226", "0960578", "0970317"],
            },
            {
                "id": "p2",
                "kind": "choose_one",
                "courseNumbers": ["0960606", "0960617", "0960690"],
            },
            {
                "id": "p3",
                "kind": "choose_one",
                "courseNumbers": [
                    "0960226",
                    "0960578",
                    "0970317",
                    "0960606",
                    "0960617",
                    "0960690",
                ],
            },
        ],
    },
    "ie-focus-chain-game-theory": {
        "type": "steps",
        "steps": [
            {
                "id": "p1",
                "kind": "choose_one",
                "courseNumbers": ["0960226", "0960570", "0960578", "0970317"],
            },
            {
                "id": "p2",
                "kind": "choose_one",
                "courseNumbers": ["0960606", "0960617", "0960690"],
            },
            {
                "id": "p3",
                "kind": "choose_one",
                "courseNumbers": [
                    "0960226",
                    "0960570",
                    "0960578",
                    "0970317",
                    "0960606",
                    "0960617",
                    "0960690",
                    "0960211",
                ],
            },
        ],
    },
    "ie-focus-chain-advanced-industry": {
        "type": "steps",
        "steps": [
            {"id": "p1", "kind": "required", "courseNumbers": ["0960411"]},
            {
                "id": "p2",
                "kind": "choose_one",
                "courseNumbers": ["0940222", "0950111", "0960210", "0970247"],
            },
            {
                "id": "p3",
                "kind": "choose_one",
                "courseNumbers": [
                    "0940222",
                    "0950111",
                    "0960210",
                    "0970247",
                    "0960208",
                    "0960266",
                    "0960625",
                    "0970139",
                    "0960135",
                    "0970244",
                ],
            },
        ],
    },
    "ie-focus-chain-operations-research": {
        "type": "steps",
        "steps": [
            {"id": "p1", "kind": "required", "courseNumbers": ["0960327"]},
            {
                "id": "p2",
                "kind": "required",
                "courseNumbers": ["0960570", "0980413"],
            },
            {
                "id": "p3",
                "kind": "choose_one",
                "courseNumbers": ["0960311", "0960335"],
            },
        ],
    },
}


def pool_group_suffix(requirement_group_id: str) -> str:
    if ":" not in requirement_group_id:
        return requirement_group_id
    return requirement_group_id.split(":", 1)[1]


def pool_chain_layout(pool_document: dict[str, Any]) -> dict[str, Any] | None:
    suffix = pool_group_suffix(str(pool_document.get("requirementGroupId") or ""))
    layout = _POOL_CHAIN_LAYOUTS.get(suffix)
    if layout is not None:
        return layout

    rule = pool_document.get("ruleExpression") or {}
    if rule.get("operator") != "choose_chain":
        return None
    if suffix in FLEXIBLE_CHAIN_SUFFIXES:
        return None
    return {
        "type": "steps",
        "steps": [{"id": "choose", "kind": "choose_one", "listing": "remaining"}],
    }
