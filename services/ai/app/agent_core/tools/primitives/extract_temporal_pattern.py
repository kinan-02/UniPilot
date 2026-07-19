"""`extract_temporal_pattern` -- mine a time-indexed historical record for a
pattern and project forward with confidence (docs/agent/AGENT_VISION.md §5,
primitive 5). Generalizes future-offering prediction (§2.3) to any
time-indexed fact.

Output shape, the `fact_type` vocabulary, the 3-bucket per-term-type
classification, and the confidence formula are all defined in
docs/agent/TEMPORAL_PATTERN_CONTRACT.md -- the single source of truth for
this primitive's contract (confirmed with the user before implementing,
since none of it has any prior art in the codebase to ground it in). Update
that doc whenever this file's vocabulary or formula changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.certainty import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.identifiers import ENTITY_ID_DESCRIPTION
from app.agent_core.tools.registry import ToolDescriptor
from app.config import get_settings
from app.retrieval.graph_engine.graph_registry import graph_registry
from app.retrieval.graph_engine.semester_catalog import OFFERING_LABELS, discover_semester_catalogs

TOOL_NAME = "extract_temporal_pattern"

_KNOWN_FACT_TYPES: frozenset[str] = frozenset({"course_offering"})


class ExtractTemporalPatternInput(BaseModel):
    fact_type: str
    entity: str = Field(description=ENTITY_ID_DESCRIPTION)


def _course_codes_in_file(path: str) -> set[str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    codes: set[str] = set()
    for entry in raw:
        code = str((entry.get("general") or {}).get("מספר מקצוע", "")).strip()
        if code:
            codes.add(code)
    return codes


def _confidence_from_history_size(total_semesters: int) -> float:
    return min(0.95, 0.5 + 0.1 * total_semesters)


def _mine_course_offering_pattern(entity: str, raw_dir: str) -> dict[str, Any]:
    catalogs = discover_semester_catalogs(Path(raw_dir))

    term_totals: dict[int, int] = {}
    term_observed: dict[int, int] = {}
    for catalog in catalogs:
        term_index = OFFERING_LABELS.get(catalog.offering_code, {}).get("plan_term")
        if term_index is None:
            continue
        term_totals[term_index] = term_totals.get(term_index, 0) + 1
        if entity in _course_codes_in_file(catalog.path):
            term_observed[term_index] = term_observed.get(term_index, 0) + 1

    term_patterns: dict[str, dict[str, Any]] = {}
    term_labels: dict[str, str] = {}
    for term_index, total in sorted(term_totals.items()):
        observed = term_observed.get(term_index, 0)
        ratio = observed / total
        if ratio == 1.0:
            label = "reliable"
        elif ratio == 0.0:
            label = "never"
        else:
            label = "irregular"
        term_patterns[str(term_index)] = {"label": label, "observed": observed, "total": total}
        term_labels[str(term_index)] = label

    return {
        "factType": "course_offering",
        "entity": entity,
        # `termPatterns` holds the full record per term; `termLabels` is a SCALAR
        # projection (term -> label) so a consumer can surface `termLabels.<n>`
        # directly instead of drilling into a term OBJECT. Both composites that
        # embed this output (get_course_profile, check_eligibility) inherit it, so
        # the offering answer has one consistent scalar grain regardless of which
        # tool the model reached for (§18.11 root fix -- tool-choice can no longer
        # change the answer's shape).
        "termPatterns": term_patterns,
        "termLabels": term_labels,
        # SCALAR count of the semesters this course actually appeared in (sum of
        # `observed` across term-types) -- the same grain principle as termLabels,
        # added so "in how many semesters has X been offered?" is a single leaf a
        # consumer can surface/compare directly, not a sum it must re-derive over
        # the term OBJECTS. It is what makes `map extract_temporal_pattern over
        # <codes>, select data.semestersOffered` yield a comparable per-course
        # count (§19 map primitive), so an argmax over many courses stays in-code
        # and grounded instead of collapsing into a child loop that gives up.
        "semestersOffered": sum(term_observed.values()),
        "totalSemestersInHistory": len(catalogs),
    }


async def run_extract_temporal_pattern(payload: ExtractTemporalPatternInput) -> ToolOutputEnvelope:
    fact_type = (payload.fact_type or "").strip()
    entity = (payload.entity or "").strip()

    if not fact_type:
        return ToolOutputEnvelope(ok=False, data=None, error="fact_type_required")
    if fact_type not in _KNOWN_FACT_TYPES:
        return ToolOutputEnvelope(ok=False, data=None, error=f"unknown_fact_type: {fact_type}")
    if not entity:
        return ToolOutputEnvelope(ok=False, data=None, error="entity_required")

    try:
        if not graph_registry.is_configured():
            return ToolOutputEnvelope(ok=False, data=None, error="academic_raw_data_not_configured")
        raw_dir = get_settings().resolved_technion_raw_dir()
        data = _mine_course_offering_pattern(entity, raw_dir)
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"academic_raw_data_unavailable: {exc}")

    if data["totalSemestersInHistory"] == 0:
        return ToolOutputEnvelope(ok=False, data=None, error="insufficient_history")

    return ToolOutputEnvelope(
        ok=True,
        data=data,
        certainty=CertaintyTag(
            basis="predicted_pattern",
            confidence=_confidence_from_history_size(data["totalSemestersInHistory"]),
        ),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Mine a time-indexed historical record for a pattern and project forward "
    "with an explicit confidence/pattern basis -- never asserted as a published fact. "
    "See docs/agent/TEMPORAL_PATTERN_CONTRACT.md for the fact_type vocabulary and output shape.",
    input_model=ExtractTemporalPatternInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_extract_temporal_pattern,
)
