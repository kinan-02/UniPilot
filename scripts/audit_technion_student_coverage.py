#!/usr/bin/env python3
"""Audit Technion wiki catalog coverage vs exportable student admission paths."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DE_ROOT = REPO_ROOT / "services" / "data-engineering"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(DE_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from lib.parallel_faculties import default_worker_count  # noqa: E402

from app.paths import catalog_vault_root  # noqa: E402
from app.vault.export_faculty_vault_catalog import faculty_wiki_id  # noqa: E402
from app.vault.loader import load_pages_by_slug, wiki_root  # noqa: E402
from app.vault.vault_export_registry import export_vault_catalog, supported_export_faculties  # noqa: E402


def _audit_faculty(payload: dict[str, object]) -> dict[str, object]:
    faculty_id = str(payload["faculty_id"])
    wiki_slugs: set[str] = set(payload["wiki_slugs"])  # type: ignore[arg-type]

    document, readiness = export_vault_catalog(faculty=faculty_id)
    programs = document.get("programs") or []
    path_options = document.get("pathOptions") or []
    wiki_id = faculty_wiki_id(faculty_id)
    exported_slugs = {(program.get("metadata") or {}).get("wikiPage") for program in programs}
    missing_tracks = sorted(wiki_slugs - exported_slugs)
    no_code = [
        (program.get("metadata") or {}).get("wikiPage")
        for program in programs
        if not program.get("programCode")
    ]
    primary_paths = [option for option in path_options if option.get("selectableAsPrimary")]
    primary_path_rows = [
        {
            "facultyExportId": faculty_id,
            "facultyWikiId": option.get("facultyId"),
            "wikiSlug": option.get("wikiSlug"),
            "kind": option.get("kind"),
            "studyLevels": option.get("studyLevels"),
            "linkedProgramCode": option.get("linkedProgramCode"),
            "nameHe": option.get("nameHe") or option.get("name"),
        }
        for option in primary_paths
    ]

    empty_pools: list[str] = []
    for program in programs:
        wiki_page = (program.get("metadata") or {}).get("wikiPage")
        for group in program.get("requirementGroups") or []:
            rule = group.get("ruleExpression") or {}
            if rule.get("operator") not in {"choose_n", "choose_chain"}:
                continue
            if not (group.get("courseReferences") or []):
                empty_pools.append(f"{faculty_id}:{wiki_page}:{group.get('groupId')}")

    summary = {
        "facultyId": faculty_id,
        "wikiFacultyId": wiki_id,
        "exportedPrograms": len(programs),
        "pathOptions": len(path_options),
        "primaryPaths": len(primary_paths),
        "canImportToStaging": readiness.get("canImportToStaging"),
        "blockingIssues": len(readiness.get("blockingIssuesForStaging") or []),
        "missingWikiTracks": missing_tracks,
        "programsWithoutCode": no_code,
    }

    gaps: list[dict[str, object]] = []
    if missing_tracks:
        gaps.append({"type": "missing_tracks", "facultyId": faculty_id, "tracks": missing_tracks})
    if no_code:
        gaps.append({"type": "missing_program_code", "facultyId": faculty_id, "tracks": no_code})
    if not readiness.get("canImportToStaging"):
        gaps.append(
            {
                "type": "staging_blocked",
                "facultyId": faculty_id,
                "issues": readiness.get("blockingIssuesForStaging") or [],
            }
        )

    return {
        "summary": summary,
        "gaps": gaps,
        "empty_pools": empty_pools,
        "primary_paths": primary_path_rows,
    }


def _collect_gaps(*, workers: int | None = None) -> dict[str, object]:
    root = wiki_root(catalog_vault_root())
    pages = load_pages_by_slug(root)
    wiki_tracks = sorted(slug for slug in pages if slug.startswith("track-"))

    faculty_track_map: dict[str, list[str]] = defaultdict(list)
    for slug in wiki_tracks:
        page = pages[slug]
        faculty = page.frontmatter.get("faculty") or "unknown"
        faculty_track_map[faculty].append(slug)

    faculty_ids = sorted(supported_export_faculties())
    payloads = [
        {
            "faculty_id": faculty_id,
            "wiki_slugs": faculty_track_map.get(faculty_wiki_id(faculty_id), []),
        }
        for faculty_id in faculty_ids
    ]

    worker_count = default_worker_count(workers)
    if worker_count == 1 or len(payloads) == 1:
        faculty_results = [_audit_faculty(payload) for payload in payloads]
    else:
        faculty_results = [None] * len(payloads)
        with ProcessPoolExecutor(max_workers=min(worker_count, len(payloads))) as pool:
            futures = {
                pool.submit(_audit_faculty, payload): index for index, payload in enumerate(payloads)
            }
            for future in as_completed(futures):
                faculty_results[futures[future]] = future.result()
        faculty_results = [result for result in faculty_results if result is not None]

    faculty_summaries: list[dict[str, object]] = []
    all_primary_paths: list[dict[str, object]] = []
    gaps: list[dict[str, object]] = []
    empty_pools: list[str] = []

    for result in faculty_results:
        faculty_summaries.append(result["summary"])
        gaps.extend(result["gaps"])
        empty_pools.extend(result["empty_pools"])
        all_primary_paths.extend(result["primary_paths"])

    exported_primary_slugs = {
        path["wikiSlug"]
        for path in all_primary_paths
        if path.get("kind") == "bsc_track"
    }
    missing_primary = sorted(set(wiki_tracks) - exported_primary_slugs - {"track-medicine-md"})

    return {
        "wikiTrackCount": len(wiki_tracks),
        "exportFacultyCount": len(faculty_ids),
        "workersUsed": min(worker_count, len(payloads)),
        "primaryAdmissionPathCount": len(all_primary_paths),
        "primaryBscTrackCount": sum(
            1 for path in all_primary_paths if path.get("kind") == "bsc_track"
        ),
        "emptyElectivePools": empty_pools,
        "wikiTracksMissingPrimaryPath": missing_primary,
        "gaps": gaps,
        "facultySummaries": faculty_summaries,
        "primaryPaths": all_primary_paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Write full audit report JSON")
    parser.add_argument("--fail-on-gaps", action="store_true", help="Exit 1 when gaps remain")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Parallel export workers (default: {default_worker_count(None)})",
    )
    args = parser.parse_args()

    report = _collect_gaps(workers=args.workers)
    print(json.dumps({k: v for k, v in report.items() if k != "primaryPaths"}, indent=2, ensure_ascii=False))

    has_gaps = bool(report["gaps"]) or bool(report["emptyElectivePools"]) or bool(
        report["wikiTracksMissingPrimaryPath"]
    )
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {args.json}")

    if args.fail_on_gaps and has_gaps:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
