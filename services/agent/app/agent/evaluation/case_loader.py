"""Load sanitized offline eval cases (Phase 23)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.evaluation.replay_schemas import EvalCase
from app.agent.evaluation.sanitizer import sanitize_eval_payload


def _load_json_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _load_jsonl_file(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            items.append(parsed)
    return items


def _collect_case_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted(path.glob("*.json")) + sorted(path.glob("*.jsonl"))
        return files
    return []


def load_eval_cases(path: str | Path, *, strict: bool = True) -> list[EvalCase]:
    """Load, validate, and sanitize eval cases. Never executes fixture content."""
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"eval_cases_not_found:{root}")

    raw_items: list[dict[str, Any]] = []
    for file_path in _collect_case_paths(root):
        if file_path.suffix == ".jsonl":
            raw_items.extend(_load_jsonl_file(file_path))
        elif file_path.suffix == ".json":
            raw_items.extend(_load_json_file(file_path))

    raw_items.sort(key=lambda item: str(item.get("id") or ""))

    cases: list[EvalCase] = []
    for item in raw_items:
        sanitized = sanitize_eval_payload(item, strict=strict)
        cases.append(EvalCase.model_validate(sanitized))
    return cases
