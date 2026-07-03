#!/usr/bin/env python3
"""HTTP E2E runner for the conversation agent benchmark.

Requires the stack:

    docker compose up --build

Run from repo root (host → localhost:8000):

    python3 scripts/run_agent_eval_http.py

Run inside the API container (in-process → localhost:8000):

    docker compose exec api python -m app.agent.evaluation.run_agent_eval_http

Optional env:
    AGENT_EVAL_API_BASE_URL   default http://localhost:8000
    AGENT_EVAL_DELAY_MS       default 6500 (AI rate-limit spacing)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "app.agent.evaluation.run_agent_eval_http",
        *sys.argv[1:],
    ]
    completed = subprocess.run(command, cwd=API_DIR, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
