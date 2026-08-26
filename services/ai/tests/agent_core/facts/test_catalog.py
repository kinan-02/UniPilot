"""The tool catalog -- phase 9b of docs/agent/tools_implementation_plan.md.

Two failure modes worth testing, both observed in the system this replaces:

**Drift.** The old prompt kept tool names in hand-maintained prose, including
cross-references inside OTHER tools' notes. A tool removed from the registry
went on being described -- which silently corrupted an ablation experiment,
because the model was still being told about a tool that was not there.

**Examples that do not run.** A prompt teaching malformed JSON is worse than one
that says nothing, since the model has no reason to doubt it. Every example here
is parsed by the real codec.
"""

from __future__ import annotations

import json
import re

import pytest

from app.agent_core.facts.catalog import COMPOSITES, PRIMITIVES, render_catalog, tool_names
from app.agent_core.facts.codec import parse_pipelines, parse_predicate
from app.agent_core.facts.operators import OPERATORS, SUGAR
from app.agent_core.facts.sources import REGISTRY


def _source_names() -> set[str]:
    """Every source name the model can actually `find`, read off the sources.

    Not a literal list. Four of them are added by `build_wiring` from the
    knowledge graph rather than declared in `REGISTRY`, so a hand-written set
    would either omit them -- failing the catalog for naming sources that DO
    exist -- or list them, and then keep approving them after they were removed.

    Built through the same constructors production uses, with a stub engine, so
    no graph has to be built to ask what a source is called.
    """
    from app.agent_core.facts import views, wiring

    stub = _NoEngine()
    return set(REGISTRY) | {
        builder(stub).collection
        for builder in (
            wiring.prerequisite_edges_source,
            wiring.curriculum_source,
            views.passed_courses_source,
            views.remaining_courses_source,
        )
    }


class _NoEngine:
    """Enough of an engine to name a source, and nothing more -- these
    constructors must not need a built graph just to say what they are called."""

    graph = None
    wiki_pages: dict = {}
    slug_to_course_code: dict = {}


class TestExamplesActuallyRun:
    def test_the_compute_example_parses(self) -> None:
        """The workhorse tool's example is the one most likely to be copied."""
        spec = next(s for s in PRIMITIVES if s.name == "compute")
        pipelines = parse_pipelines(spec.example["args"]["pipelines"])
        assert len(pipelines) == 2
        # Either reference mechanism counts. A pipeline may chain by taking the
        # previous one as its `source`, or by naming it in `other` -- and the
        # `other` form is the one worth teaching, since cross-pipeline arithmetic
        # is where a model is most tempted to type a literal instead.
        referenced = {pipelines[1].source} | {
            stage.args.get("other") for stage in pipelines[1].stages
        }
        assert pipelines[0].name in referenced, "the example should demonstrate chaining"

    def test_the_find_example_predicate_parses(self) -> None:
        spec = next(s for s in PRIMITIVES if s.name == "find")
        assert parse_predicate(spec.example["args"]["predicate"]) is not None

    @pytest.mark.parametrize("spec", PRIMITIVES + COMPOSITES, ids=lambda s: s.name)
    def test_every_example_is_valid_json_naming_its_own_tool(self, spec) -> None:
        json.dumps(spec.example)
        assert spec.example["tool"] == spec.name, "an example must call the tool it documents"
        assert "args" in spec.example


class TestNoDrift:
    def test_every_operator_appears_in_the_rendered_catalog(self) -> None:
        rendered = render_catalog()
        missing = [name for name in OPERATORS if name not in rendered]
        assert not missing, f"operators the model is never told about: {missing}"

    def test_every_sugar_appears_with_its_expansion(self) -> None:
        rendered = render_catalog()
        for name, expansion in SUGAR.items():
            assert name in rendered
            assert expansion in rendered, f"{name} is named without saying what to write instead"

    def test_the_operator_list_is_derived_not_transcribed(self) -> None:
        """The anti-drift property itself: add an operator and the prompt must
        change without anyone editing prose."""
        from dataclasses import replace

        before = render_catalog()
        invented = replace(OPERATORS["select"], name="frobnicate", summary="a made-up operator")
        OPERATORS["frobnicate"] = invented
        try:
            after = render_catalog()
        finally:
            del OPERATORS["frobnicate"]
        assert "frobnicate" in after and "frobnicate" not in before

    def test_the_catalog_mentions_no_tool_that_does_not_exist(self) -> None:
        """The exact bug that corrupted the ablation run: a name surviving in
        prose after the tool behind it was gone.

        Checked against snake_case words in the text rather than a curated list,
        because a curated list would need the same maintenance the prose did.
        """
        rendered = render_catalog()
        real = tool_names() | set(OPERATORS) | set(SUGAR) | _source_names()
        known_vocabulary = real | {
            # wire keys and argument names, not tools
            "search_corpus", "track_requirements", "remaining_required",
            "past_offerings", "upcoming_semesters", "period_path", "cycle_path",
            "minimize_slots", "eligibility_check", "courseNumber", "creditsEarned",
            "balance_load", "slot_index", "item_id", "slot_id",
            # Illustrative FACT names in the examples -- a model invents these,
            # they are not part of the system's vocabulary.
            "still_needed", "prereq_edges", "prereqs_met", "courses_to_place", "my_semesters",
            "next_course", "all_groups", "met_groups",
            # The `as` result-names shown in the tool examples (also invented).
            "my_courses", "policy_hits", "prereq_chain", "required_credits", "spring_forecast",
            "elective_codes", "winter_plan",
            # plan_term argument names.
            "max_credits",
        }
        mentioned = set(re.findall(r"\b[a-z]+_[a-z_]+\b", rendered))
        unknown = mentioned - known_vocabulary
        assert not unknown, f"catalog mentions unrecognised identifiers: {sorted(unknown)}"

    def test_the_system_prompt_can_actually_be_built(self) -> None:
        """`build_system_prompt` imports `render_sources` from `loop` INSIDE the
        function body, so a rename in `loop.py` breaks it at call time and not at
        import time.

        That happened. `adapter.py` was ported from the standalone agent, where
        the function is public, while this repo still called it `_render_sources`
        -- and the whole suite stayed green because nothing built a system prompt
        with the real modules. The agent could not have answered a single
        question.
        """
        from app.agent_core.facts.adapter import build_system_prompt
        from app.agent_core.facts.dispatch import DispatchContext

        prompt = build_system_prompt(DispatchContext(schemas=REGISTRY))
        assert "## compute" in prompt, "the catalog must reach the system prompt"
        assert "data sources" in prompt, "the source list must reach the system prompt"

    def test_the_source_vocabulary_is_derived_not_transcribed(self) -> None:
        """`_source_names` must actually read the sources, or the test above
        degrades into a hand-maintained list that approves whatever is added to
        it -- which is how a catalog came to advertise `remaining_courses` while
        no such source existed."""
        names = _source_names()
        assert {"completed_courses", "prerequisite_edges", "track_courses"} <= names
        assert "definitely_not_a_source" not in names


class TestWhatTheModelIsTold:
    def test_find_says_identity_is_just_a_predicate(self) -> None:
        """Without this the model looks for a get-by-id tool, does not find one,
        and either invents it or gives up."""
        spec = next(s for s in PRIMITIVES if s.name == "find")
        assert "identity" in spec.when.lower()

    def test_compute_advises_one_call_with_several_pipelines(self) -> None:
        """The turn-cost fix only pays if the model actually batches."""
        spec = next(s for s in PRIMITIVES if s.name == "compute")
        assert "one" in spec.when.lower() and "pipeline" in spec.when.lower()

    def test_interpret_forbids_calculating(self) -> None:
        spec = next(s for s in PRIMITIVES if s.name == "interpret")
        assert "never calculate" in spec.when.lower() or "extract" in spec.when.lower()

    def test_traverse_explains_why_compute_cannot_do_it(self) -> None:
        """A tool whose necessity is unexplained gets skipped in favour of the
        familiar one.

        Matched on concepts rather than an exact phrase: these guard against
        someone deleting the guidance, not against them rewording it.
        """
        spec = next(s for s in PRIMITIVES if s.name == "traverse")
        text = spec.when.lower()
        assert "compute" in text and "cannot" in text

    def test_propose_states_that_nothing_happens_without_approval(self) -> None:
        spec = next(s for s in PRIMITIVES if s.name == "propose")
        assert "nothing" in spec.purpose.lower()

    def test_forecast_requires_a_complete_history(self) -> None:
        spec = next(s for s in PRIMITIVES if s.name == "forecast")
        assert "whole" in spec.when.lower() or "complete" in spec.when.lower()


class TestShape:
    def test_there_are_exactly_nine_primitives(self) -> None:
        """Eight from the original derivation, plus `extract_list` -- the grounded
        PLURAL of `interpret`. Its boundary argument: reading a set the wiki
        already lists (which courses are electives) is retrieval, not a new kind
        of reasoning, and the alternative was pre-baking the classification into
        the graph -- the composite anti-pattern this set exists to avoid. If this
        number moves again, something was added without an argument that clean."""
        assert len(PRIMITIVES) == 9

    def test_plan_term_is_a_quarantined_composite_not_a_primitive(self) -> None:
        """The composite the primitive set exists to avoid lives in COMPOSITES, so
        the nine-primitives invariant stays honest while the shortcut is still
        advertised and callable."""
        assert [spec.name for spec in COMPOSITES] == ["plan_term"]
        assert "plan_term" not in {spec.name for spec in PRIMITIVES}
        assert "plan_term" in tool_names()

    def test_names_are_unique(self) -> None:
        assert len(tool_names()) == len(PRIMITIVES) + len(COMPOSITES)
