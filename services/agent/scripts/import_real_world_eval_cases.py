#!/usr/bin/env python3
"""Import anonymized real-world cases into offline eval fixtures (Phase 26)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from app.agent.evaluation.real_world_importer import (
    import_real_world_cases,
    load_real_world_case_inputs,
    write_eval_case_files,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import anonymized real-world cases into EvalCase fixtures.")
    parser.add_argument("--input", required=True, help="JSON/JSONL file or directory")
    parser.add_argument("--output-dir", required=True, help="Directory for generated EvalCase JSON files")
    parser.add_argument("--strict", action="store_true", default=True)
    parser.add_argument("--no-strict", action="store_false", dest="strict")
    parser.add_argument("--prefix", default="real_world")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    inputs = load_real_world_case_inputs(args.input)
    cases, warnings = import_real_world_cases(inputs, prefix=args.prefix, strict=args.strict)

    summary = {
        "inputCount": len(inputs),
        "outputCount": len(cases),
        "warnings": warnings[:20],
        "dryRun": bool(args.dry_run),
        "caseIds": [case.id for case in cases],
    }

    if args.dry_run:
        print(json.dumps(summary))
        return

    written = write_eval_case_files(cases, args.output_dir)
    summary["writtenFiles"] = [str(path) for path in written]
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
