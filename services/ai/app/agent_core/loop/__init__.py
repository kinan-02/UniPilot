"""The V2 agent loop (docs/agent/AGENT_ARCHITECTURE_V2.md).

A single thinking-ON reasoning loop over a fabrication-proof substrate, replacing
V1's orchestration org chart. `run_agent_loop` is the entry point.

**SUPERSEDED, and deliberately not re-exported here.** `/advise` runs the
grounded facts loop in `app/agent_core/facts/` instead; nothing in `app/` calls
`run_agent_loop` any more. Import it from `app.agent_core.loop.runner` if you
want it.

This file used to re-export it eagerly. `app/main.py` imports
`load_catalog_names` from `course_names` in this package, so that one line pulled
the whole superseded tree -- and the V1 tool layer underneath it -- into every
process, behind an import nobody could see.

    import app.agent_core.loop.course_names, with the re-export  ->  1090 modules
    without it                                                   ->  1019 modules

**The saving is 71 modules and almost no time**, which is worth stating plainly
because the tempting claim is that this fixes cold start. It does not:
`course_names` needs `graph_registry`, and that alone is 1,015 modules and ~970ms.
The graph engine is the cold start; this tree was riding along beside it.

The reason to do it anyway is that a package `__init__` importing its own
subpackages turns "is this dead?" into a question static analysis answers WRONG.
An import closure from `app.main` reported all 42 of these modules as reachable,
because they are -- just never called. Removing the re-export makes the closure
tell the truth, which is what any future teardown has to start from.
"""

from __future__ import annotations

__all__: list[str] = []
