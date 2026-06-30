#!/usr/bin/env python3
"""CLI compatibility wrapper: JSON stdin → graph_registry → JSON stdout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.graph_registry import graph_registry  # noqa: E402


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "data": None, "error": f"Invalid JSON input: {exc}"}))
        return

    success, data, error = graph_registry.dispatch_action(payload)
    print(json.dumps({"success": success, "data": data, "error": error}, ensure_ascii=False))


if __name__ == "__main__":
    main()
