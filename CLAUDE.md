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

The ECC plugin (`ecc@ecc`) only loads in a terminal CLI session (`/plugin` isn't supported in the
VS Code extension chat surface as of extension v2.1.206). For chat sessions, a curated subset of
ECC's skills and agents — matched to this repo's actual stack — is copied directly into
`.claude/skills/` and `.claude/agents/`, which Claude Code loads natively in any session, plugin or
not:

- **Skills**: `python-patterns`, `python-testing`, `fastapi-patterns`, `react-patterns`,
  `react-testing`, `react-performance`, `frontend-patterns`, `frontend-a11y`, `api-design`,
  `security-review`, `security-scan`, `tdd-workflow`, `verification-loop`, `e2e-testing`,
  `docker-patterns`, `redis-patterns`, `mcp-server-patterns`, `error-handling`
- **Agents**: `python-reviewer`, `fastapi-reviewer`, `react-reviewer`, `typescript-reviewer`,
  `security-reviewer`, `database-reviewer`, `code-explorer`, `docs-lookup`, `e2e-runner`

These are a deliberate subset, not the full ECC bundle (172 skills / 66 agents) — only what matches
this repo's Python/FastAPI + MongoDB/Redis backend and React/TS frontend. ECC's hooks were
intentionally **not** copied here to avoid double-running against the plugin's own hooks in a CLI
session; hook-based automation (e.g. auto-formatting) is CLI-only for now. When adding a new ECC
skill/agent to this set, copy it from the plugin's own cache
(`~/.claude/plugins/cache/ecc/ecc/<version>/{skills,agents}/`) rather than re-cloning the ECC repo.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
