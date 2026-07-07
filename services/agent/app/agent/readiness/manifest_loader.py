"""Load human-reviewed runtime promotion activation manifests (Phase 25)."""

from __future__ import annotations

import json
from pathlib import Path

from app.agent.readiness.schemas import RuntimeReadinessCandidateApproval, RuntimeReadinessManifest


def load_runtime_readiness_manifest(path: str | Path) -> RuntimeReadinessManifest | None:
    """Load and validate a JSON activation manifest. Never executes content."""
    try:
        file_path = Path(path)
        if not file_path.is_file():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        manifest = RuntimeReadinessManifest.model_validate(data)
        sorted_candidates = sorted(manifest.candidates, key=lambda item: item.candidate_id)
        return manifest.model_copy(update={"candidates": sorted_candidates})
    except Exception:  # noqa: BLE001
        return None


def find_manifest_candidate(
    manifest: RuntimeReadinessManifest,
    candidate_id: str,
) -> RuntimeReadinessCandidateApproval | None:
    for candidate in manifest.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    return None
