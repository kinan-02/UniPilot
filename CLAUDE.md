# UniPilot — Claude Code Instructions

## Precedence

This file and anything under `.claude/rules/` (project-specific) take precedence over generic
guidance from the ECC plugin's skills, agents, commands, and `.claude/rules/ecc/` rule packs.
When they conflict, follow the project-specific instruction.

## Working in this repo

- Inspect existing patterns in the relevant `services/*` directory before writing or changing code —
  don't introduce a new convention where an established one already exists.
- Run the project's actual tests/build for whatever you touched before reporting a task done.
  Passing type checks is not the same as a verified fix.
- Don't refactor, reformat, or restructure code beyond what the task requires.
- Destructive or high-risk operations (force-push, `git reset --hard`, deleting data, dropping
  services, modifying CI) require explicit approval before running.
- Existing project scripts, Docker Compose services, and docs (`docs/`, service READMEs) are the
  authoritative source for how to run/build/test this repo — prefer them over inventing new commands.

## Using ECC

Use the ECC plugin's skills and agents when they fit the task at hand (e.g. `python-reviewer`,
`react-reviewer`, `fastapi-patterns`, `tdd-workflow`). ECC rule packs relevant to this repo live at
`.claude/rules/ecc/{common,python,typescript,react,web}/`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
