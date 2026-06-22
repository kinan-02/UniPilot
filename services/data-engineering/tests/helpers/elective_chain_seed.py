"""Contract-compliant elective chain fields for data-engineering test seeds."""

from __future__ import annotations

from typing import Any

from app.vault.elective_chain_contract import iter_contract_pools

# Mirror services/api/app/curriculum/pool_course_enrichment.py for stable CI seeds.
_CHOOSE_N_CHAIN_FALLBACK_NUMBERS: dict[str, tuple[str, ...]] = {
    "ie-statistics-elective-chain": (
        "0960414",
        "0960415",
        "0960425",
        "0960450",
        "0960465",
        "0960475",
        "0970414",
        "0970449",
    ),
    "ie-behavior-science-chain": ("0960600", "0960620"),
    "is-behavior-science-chain": ("0960600", "0960620"),
}

_FOCUS_CHAIN_FALLBACK_NUMBERS: dict[str, tuple[str, ...]] = {
    "is-focus-chain-performance": (
        "0960327",
        "0960324",
        "0980413",
        "0960311",
        "0960335",
        "0960351",
        "0970135",
        "0970280",
        "0970325",
        "0970334",
    ),
    "is-focus-chain-ml": (
        "0970209",
        "0960212",
        "0960327",
        "0970414",
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
    ),
    "is-focus-chain-game-theory": (
        "0960226",
        "0960578",
        "0970317",
        "0960606",
        "0960617",
        "0960690",
    ),
    "ie-focus-chain-game-theory": (
        "0960226",
        "0960570",
        "0960578",
        "0970317",
        "0960606",
        "0960617",
        "0960690",
        "0960211",
    ),
    "ie-focus-chain-advanced-industry": (
        "0960411",
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
    ),
    "ie-focus-chain-operations-research": (
        "0960327",
        "0960570",
        "0980413",
        "0960311",
        "0960335",
    ),
}


def _fallback_numbers(suffix: str) -> tuple[str, ...]:
    return _CHOOSE_N_CHAIN_FALLBACK_NUMBERS.get(suffix) or _FOCUS_CHAIN_FALLBACK_NUMBERS.get(suffix, ())


def _contract_entry(group_id: str) -> dict[str, Any] | None:
    suffix = group_id.split(":")[-1]
    program_code = group_id.split(":")[0]
    return next(
        (
            entry
            for entry in iter_contract_pools(faculty_id="dds")
            if entry.get("suffix") == suffix and entry.get("programCode") == program_code
        ),
        None,
    )


def build_advisory_requirement_group_fields(group_id: str) -> dict[str, Any]:
    """Return requirementGroup sub-document fields satisfying the elective chain contract."""
    entry = _contract_entry(group_id)
    if entry is None:
        if "semester-" in group_id:
            return {
                "courseReferences": [],
                "ruleExpression": {"type": "semester_matrix", "operator": "all_of"},
            }
        return {
            "courseReferences": [],
            "ruleExpression": {"type": "course_pool", "operator": "min_credits"},
        }

    suffix = str(entry["suffix"])
    min_refs = int(entry.get("minCourseRefs") or 0)
    numbers = [number.zfill(8) for number in _fallback_numbers(suffix)]
    for required in entry.get("mustIncludeCourseNumbers") or []:
        padded = str(required).zfill(8)
        if padded not in numbers:
            numbers.insert(0, padded)
    while len(numbers) < min_refs:
        numbers.append(f"09603{len(numbers):03d}")

    operator = str(entry.get("operator") or "choose_n")
    rule_expression: dict[str, Any] = {"type": "course_pool", "operator": operator}
    if operator == "choose_n":
        rule_expression["chooseCount"] = 1

    fields: dict[str, Any] = {
        "courseReferences": [
            {"courseNumber": number, "titleHint": f"Seed {number}"} for number in numbers[:min_refs]
        ],
        "ruleExpression": rule_expression,
    }
    if entry.get("requiresCatalogDescription"):
        fields["catalogDescription"] = f"Contract seed for {group_id}"
    return fields
