"""Fixtures for the loop package's tests.

`course_names` reads the real catalog through the shared `graph_registry`, so it
needs the same real-engine fixtures the tool tests use. Re-exported rather than
moved up a level so the existing `tests/agent_core/tools` suite is untouched;
`real_academic_engine` stays session-scoped, so both packages share one build.
"""

from __future__ import annotations

from tests.agent_core.tools.conftest import (  # noqa: F401 -- pytest fixture injection
    real_academic_engine,
    use_real_academic_engine,
)
