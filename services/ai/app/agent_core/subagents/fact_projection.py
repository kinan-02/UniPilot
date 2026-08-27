"""Build a retrieval step's `facts` FROM its tool results, in code.

Retrieval fetches; it cannot compute. That invariant was previously enforced by
inspecting what the model *said* about each fact -- `_drop_ungrounded_facts`
read the model-authored `source` string and dropped any fact whose citation
named no invoked tool. Measured live (2026-07-16, ise_correctness
`presupposition_conflict`) that guard deleted three genuine facts:

    {"key": "degree_program", "value": "track-information-systems-engineering",
     "source": "student_profile.programSlug", "confidence": "high"}

`student_profile.programSlug` cites the entity and field rather than the
function, so it matched no tool name and was dropped -- while the identical
values fetched by the identical `get_entity` call in the `credits_remaining`
case survived, because that model happened to write `get_entity(student_profile)`.
Same tool, same data, different prose, opposite verdict. The step lost 100% of
its facts and still reported `succeeded`.

Worse, the guard could only ever catch a model that CONFESSED. The fabrication
it was written for --

    {"key": "totalCreditsEarned", "value": 63.0,
     "source": "sum of creditsEarned across all 17 completed courses"}

-- was caught solely because the model described its own arithmetic in the
citation field. The same invented 63.0 carrying `"source": "get_entity(...)"`
would have passed. A check on a field the model writes is not a check; it is a
self-report, and its true-positive rate is the model's candour.

So this module does not check. It CONSTRUCTS. The model emits selectors --
"fact `completedCourses` is at `data.completedCourses` of call_2" -- and the
value is read out of the recorded tool envelope by `resolve_path`. Groundedness
stops being a property we verify and becomes a property of how the value got
there: there is no syntax in which the model can express a number, so `63.0`
cannot be written down, and `source`/`confidence` are generated here from the
call that actually ran rather than being taken on trust.

A selector is a PATH. Anything needing an operator (a sum, a count, a filter, a
comparison) is a derivation and belongs to `calculation_validation`, whose
`expression_tree` already has `sum`/`count`/`where`/`field` for exactly this.
The line is structural rather than a judgement about which operators feel
innocent -- which is the same reason the old citation guard could not hold one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Deliberately shallow. These exist to let a model repair a mistyped path, not
# to render the document -- a student_profile walked without bound enumerates
# every nested selection in `academicPath`, which is noise in an error message
# and tokens in a prompt.
_MAX_PATH_DEPTH = 3
_MAX_PATHS_LISTED = 40


def build_call_handles(tool_results: dict[str, Any]) -> dict[str, str]:
    """Map a short, model-facing handle onto each recorded tool call.

    `tool_round.execute_tool_round` keys its results by
    `f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"`, e.g.

        get_entity:{"entity_id": "6a58b4a0c24b4bfb42aa27f3", "entity_type": "student_profile"}

    That key is a faithful identifier and a terrible thing to ask a model to
    reproduce: making it echo one back would reintroduce, in the reference,
    exactly the transcription this module exists to remove. `call_1`/`call_2`
    are addressable in a handful of tokens and cannot be misspelled into a
    different valid call.

    Insertion order is the assignment order. `tool_results_so_far` accumulates
    across rounds and `execute_tool_round` merges into a copy, so a handle is
    stable for the life of one block run -- including cache hits, which merge
    under the same result key they would have had.
    """
    return {f"call_{index}": key for index, key in enumerate(tool_results, start=1)}


def describe_call(result_key: str) -> str:
    """Render a result key as the fact's `source` citation.

    The key already IS the citation -- tool name and arguments, verbatim, from
    the call that ran. Generating `source` here rather than asking the model for
    it is what makes the field trustworthy: it is a record, not a claim.
    """
    tool_name, _, arguments = result_key.partition(":")
    if not arguments:
        return tool_name
    try:
        parsed = json.loads(arguments)
    except (ValueError, TypeError):
        return tool_name
    if not isinstance(parsed, dict) or not parsed:
        return tool_name
    rendered = ", ".join(f"{key}={parsed[key]}" for key in sorted(parsed))
    return f"{tool_name}({rendered})"


def resolve_path(node: Any, path: str) -> tuple[Any, bool]:
    """Walk a dotted path into a recorded tool envelope.

    Returns `(value, found)`. `found` is False for a missing key or a non-dict
    intermediate -- distinguishing "the path is wrong" from "the path is right
    and the value is legitimately None/[]/0", which a sentinel return could not.

    No wildcards, no indices, no predicates: none of the six live
    ise_correctness cases needed one, and a selector that can filter is a
    selector that can derive.
    """
    if not path:
        return None, False
    current = node
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None, False
        current = current[segment]
    return current, True


def available_paths(node: Any, *, prefix: str = "", depth: int = 0) -> list[str]:
    """Enumerate the dotted paths a model could legally select from an envelope.

    Feeds the repair message. An error a model cannot act on gets retried
    verbatim -- measured live (2026-07-16, `credits_remaining`), where
    `non_numeric_operand: subtract` named neither operand and the identical
    failing expression came back twice.
    """
    if depth > _MAX_PATH_DEPTH or not isinstance(node, dict):
        return []
    paths: list[str] = []
    for key, value in node.items():
        here = f"{prefix}.{key}" if prefix else key
        paths.append(here)
        paths.extend(available_paths(value, prefix=here, depth=depth + 1))
    return paths[:_MAX_PATHS_LISTED]


@dataclass(frozen=True)
class ProjectionOutcome:
    """`facts` is the canonical `{key: {key, value, source, confidence}}` map the
    rest of the pipeline already consumes (`state_index`, the calculation
    block's `_unwrap_fact_envelope`/`_promote_inner_facts`) -- projection
    changes who authors a fact, never its shape downstream.

    `errors` are per-selector and phrased for repair. `bases`/`confidences`
    carry the certainty of every call actually read, so the caller can tag the
    step from its sources instead of asking the model to assert one.

    Asking is what fails today. `certainty_basis` is a field models routinely
    omit -- live (2026-07-16, `presupposition_conflict` step 1a) the retrieval
    result carried none -- and `result_normalizer`'s defaults then backfill the
    absent field with `"llm_interpretation"`, the most conservative basis. So a
    plain `get_entity(student_profile)` read ended up tagged as model guesswork
    while the tool that served it had already declared
    `CertaintyTag(basis="official_record", confidence=1.0)`. The envelope knew;
    nobody asked it.
    """

    facts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)


def project_facts(
    selectors: Any, tool_results: dict[str, Any], handles: dict[str, str]
) -> ProjectionOutcome:
    """Resolve `[{key, from, path}, ...]` against the recorded tool envelopes.

    Every failure is reported rather than silently skipped: a selector that
    resolves to nothing must surface as a repairable error, never as a fact
    quietly missing from the map. Dropping data without saying so is what let a
    step publish `facts: {}` at confidence 0.9 for a whole live run.
    """
    if not isinstance(selectors, list):
        return ProjectionOutcome(
            errors=[f"facts must be a list of selectors, got {type(selectors).__name__}"]
        )

    facts: dict[str, Any] = {}
    errors: list[str] = []
    bases: list[str] = []
    confidences: list[float] = []

    for position, selector in enumerate(selectors):
        if not isinstance(selector, dict):
            errors.append(f"facts[{position}]: expected an object with key/from/path")
            continue

        key = selector.get("key")
        handle = selector.get("from")
        path = selector.get("path")

        if not isinstance(key, str) or not key.strip():
            errors.append(f"facts[{position}]: missing 'key'")
            continue
        if handle not in handles:
            errors.append(
                f"facts[{position}] ({key}): 'from' must name a recorded call. "
                f"Got {handle!r}; available: {sorted(handles)}"
            )
            continue

        envelope = tool_results.get(handles[handle])
        if not isinstance(envelope, dict):
            errors.append(f"facts[{position}] ({key}): {handle} has no recorded result")
            continue

        if not isinstance(path, str) or not path.strip():
            errors.append(
                f"facts[{position}] ({key}): missing 'path'. "
                f"Available paths on {handle}: {available_paths(envelope)}"
            )
            continue

        value, found = resolve_path(envelope, path)
        if not found:
            errors.append(
                f"facts[{position}] ({key}): path {path!r} does not exist on {handle}. "
                f"Available paths: {available_paths(envelope)}"
            )
            continue

        certainty = envelope.get("certainty")
        confidence = 1.0
        if isinstance(certainty, dict):
            basis = certainty.get("basis")
            if isinstance(basis, str):
                bases.append(basis)
            raw_confidence = certainty.get("confidence")
            if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
                confidence = float(raw_confidence)
                confidences.append(confidence)

        facts[key] = {
            "key": key,
            "value": value,
            "source": describe_call(handles[handle]),
            "confidence": confidence,
        }

    return ProjectionOutcome(facts=facts, errors=errors, bases=bases, confidences=confidences)


__all__ = [
    "ProjectionOutcome",
    "available_paths",
    "build_call_handles",
    "describe_call",
    "project_facts",
    "resolve_path",
]
