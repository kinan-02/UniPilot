#!/usr/bin/env python3
"""Audit primary BSc track path options for missing or empty elective pools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DE_ROOT = REPO_ROOT / "services" / "data-engineering"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(DE_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from lib.parallel_faculties import default_worker_count, map_faculties_parallel  # noqa: E402

from app.paths import catalog_vault_root  # noqa: E402
from app.vault.elective_chain_contract import validate_elective_chain_export  # noqa: E402
from app.vault.loader import load_pages_by_slug, wiki_root  # noqa: E402
from app.vault.export_faculty_vault_catalog import canonical_program_track_slug  # noqa: E402
from app.vault.vault_export_registry import export_vault_catalog, supported_export_faculties  # noqa: E402

_CHOOSE_OPERATORS = frozenset({"choose_n", "choose_chain"})


def _program_for_slug(
    document: dict,
    wiki_slug: str,
    *,
    pages: dict | None = None,
) -> dict | None:
    for program in document.get("programs") or []:
        if (program.get("metadata") or {}).get("wikiPage") == wiki_slug:
            return program
    if pages is not None:
        page = pages.get(wiki_slug)
        if page is not None:
            canonical = canonical_program_track_slug(page)
            if canonical and canonical != wiki_slug:
                return _program_for_slug(document, canonical, pages=pages)
    return None


def _choose_pools(program: dict) -> list[dict]:
    pools: list[dict] = []
    for group in program.get("requirementGroups") or []:
        rule = group.get("ruleExpression") or {}
        if rule.get("operator") not in _CHOOSE_OPERATORS:
            continue
        pools.append(group)
    return pools


def _audit_faculty(faculty_id: str) -> dict[str, object]:
    document, _ = export_vault_catalog(faculty=faculty_id)
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    path_options = document.get("pathOptions") or []
    primary_tracks = [
        option
        for option in path_options
        if option.get("kind") == "bsc_track" and option.get("selectableAsPrimary")
    ]

    gaps: list[dict[str, object]] = []
    track_rows: list[dict[str, object]] = []

    for option in primary_tracks:
        wiki_slug = str(option.get("wikiSlug") or "")
        program = _program_for_slug(document, wiki_slug, pages=pages)
        pools = _choose_pools(program) if program is not None else []
        non_empty = [pool for pool in pools if pool.get("courseReferences")]
        empty_pool_ids = [
            str(pool.get("groupId") or "")
            for pool in pools
            if not (pool.get("courseReferences") or [])
        ]

        row = {
            "facultyId": faculty_id,
            "wikiSlug": wiki_slug,
            "linkedProgramCode": option.get("linkedProgramCode"),
            "poolCount": len(non_empty),
            "emptyPools": empty_pool_ids,
            "zeroPools": len(non_empty) == 0,
        }
        track_rows.append(row)

        if program is None:
            gaps.append(
                {
                    "type": "missing_program",
                    "facultyId": faculty_id,
                    "wikiSlug": wiki_slug,
                }
            )
        elif not non_empty:
            gaps.append(
                {
                    "type": "zeroPools",
                    "facultyId": faculty_id,
                    "wikiSlug": wiki_slug,
                }
            )
        elif empty_pool_ids:
            gaps.append(
                {
                    "type": "emptyPools",
                    "facultyId": faculty_id,
                    "wikiSlug": wiki_slug,
                    "groupIds": empty_pool_ids,
                }
            )

    contract_violations = validate_elective_chain_export(document, faculty_id=faculty_id)
    for violation in contract_violations:
        gaps.append(
            {
                "type": "contractViolation",
                "facultyId": faculty_id,
                "message": violation,
            }
        )

    return {
        "facultyId": faculty_id,
        "primaryTracks": len(primary_tracks),
        "gaps": gaps,
        "tracks": track_rows,
        "contractViolations": contract_violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=None, help="Parallel worker count")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    faculty_ids = sorted(supported_export_faculties())
    worker_count = default_worker_count(args.workers)
    results = map_faculties_parallel(faculty_ids, _audit_faculty, workers=worker_count)

    all_gaps: list[dict[str, object]] = []
    all_tracks: list[dict[str, object]] = []
    for result in results:
        all_gaps.extend(result["gaps"])  # type: ignore[arg-type]
        all_tracks.extend(result["tracks"])  # type: ignore[arg-type]

    report = {
        "status": "pass" if not all_gaps else "fail",
        "facultiesAudited": len(faculty_ids),
        "primaryTracks": len(all_tracks),
        "gapCount": len(all_gaps),
        "gaps": all_gaps,
        "tracks": all_tracks,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        zero_pool_tracks = [row for row in all_tracks if row.get("zeroPools")]
        print(json.dumps({"status": report["status"], "gapCount": report["gapCount"], "zeroPools": zero_pool_tracks}, indent=2))

    return 1 if all_gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
