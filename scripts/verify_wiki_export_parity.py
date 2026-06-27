#!/usr/bin/env python3
"""Verify exported catalog documents match the wiki vault (wiki is truth)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DE_ROOT = REPO_ROOT / "services" / "data-engineering"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(DE_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from lib.parallel_faculties import default_worker_count  # noqa: E402

from app.paths import catalog_vault_root  # noqa: E402
from app.vault.export_faculty_vault_catalog import (  # noqa: E402
    canonical_program_track_slug,
    discover_faculty_track_slugs,
    extract_program_code,
    faculty_wiki_id,
    should_export_degree_program,
)
from app.vault.loader import load_pages_by_slug, wiki_root  # noqa: E402
from app.vault.vault_export_registry import export_vault_catalog, supported_export_faculties  # noqa: E402


@dataclass
class FacultyParityResult:
    faculty_id: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers


def _wiki_track_codes(pages: dict, wiki_slugs: list[str]) -> dict[str, str | None]:
    codes: dict[str, str | None] = {}
    for slug in wiki_slugs:
        page = pages.get(slug)
        codes[slug] = extract_program_code(page) if page else None
    return codes


def _program_for_slug(
    document: dict,
    wiki_slug: str,
    *,
    pages: dict | None = None,
) -> dict | None:
    exported_by_wiki = {
        (program.get("metadata") or {}).get("wikiPage"): program
        for program in document.get("programs") or []
    }
    program = exported_by_wiki.get(wiki_slug)
    if program is not None:
        return program
    if pages is None:
        return None
    page = pages.get(wiki_slug)
    if page is None:
        return None
    canonical = canonical_program_track_slug(page)
    if canonical and canonical != wiki_slug:
        return exported_by_wiki.get(canonical)
    return None


def _audit_faculty_parity(payload: dict[str, object]) -> FacultyParityResult:
  faculty_id = str(payload["faculty_id"])
  wiki_slugs: list[str] = list(payload["wiki_slugs"])  # type: ignore[arg-type]
  exportable_slugs: list[str] = list(payload["exportable_slugs"])  # type: ignore[arg-type]
  wiki_codes: dict[str, str | None] = dict(payload["wiki_codes"])  # type: ignore[arg-type]

  result = FacultyParityResult(faculty_id=faculty_id)
  pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
  document, readiness = export_vault_catalog(faculty=faculty_id)
  programs = document.get("programs") or []
  path_options = document.get("pathOptions") or []

  exported_by_wiki = {
    (program.get("metadata") or {}).get("wikiPage"): program for program in programs
  }
  exported_slugs = set(exported_by_wiki) - {None}

  skipped_slugs = sorted(set(wiki_slugs) - set(exportable_slugs))
  if skipped_slugs:
    result.info.append(
      f"{len(skipped_slugs)} wiki tracks intentionally omitted from degree export "
      "(specialization or in-faculty canonical mirror pages)"
    )

  missing = sorted(set(exportable_slugs) - exported_slugs)
  for slug in missing:
    result.blockers.append(f"wiki track {slug} missing from exported programs")

  for slug in sorted(exported_slugs - set(wiki_slugs)):
    if slug and slug.startswith("track-"):
      result.warnings.append(f"exported program {slug} has no wiki track page in faculty scope")

  for slug, wiki_code in wiki_codes.items():
    program = _program_for_slug(document, slug, pages=pages)
    if not program or not wiki_code:
      continue
    export_code = program.get("programCode")
    if export_code != wiki_code:
      result.blockers.append(
        f"{slug}: wiki program code {wiki_code} != export {export_code}"
      )

  primary_bsc = {
    option.get("wikiSlug")
    for option in path_options
    if option.get("kind") == "bsc_track" and option.get("selectableAsPrimary")
  }
  for slug in wiki_slugs:
    if slug == "track-medicine-md":
      if slug in primary_bsc:
        result.blockers.append("track-medicine-md must not be primary admission path")
      continue
    if slug not in primary_bsc:
      result.warnings.append(f"{slug}: no primary bsc_track path option")

  for option in path_options:
    if option.get("kind") != "bsc_track":
      continue
    slug = option.get("wikiSlug")
    linked = option.get("linkedProgramCode")
    program = _program_for_slug(document, str(slug or ""), pages=pages)
    if program and linked and program.get("programCode") != linked:
      result.blockers.append(
        f"path option {slug}: linkedProgramCode {linked} != program {program.get('programCode')}"
      )

  counts = readiness.get("counts") or {}
  missing_hints = int(counts.get("missingTitleHints") or 0)
  if missing_hints:
    result.warnings.append(f"{missing_hints} course references lack titleHint")

  if not readiness.get("canImportToStaging"):
    for issue in readiness.get("blockingIssuesForStaging") or []:
      result.blockers.append(f"staging blocked: {issue}")

  empty_pools = 0
  for program in programs:
    wiki_page = (program.get("metadata") or {}).get("wikiPage")
    for group in program.get("requirementGroups") or []:
      rule = group.get("ruleExpression") or {}
      if rule.get("operator") not in {"choose_n", "choose_chain"}:
        continue
      if not (group.get("courseReferences") or []):
        empty_pools += 1
        result.blockers.append(
          f"{wiki_page}: empty elective pool {group.get('groupId')}"
        )
  if empty_pools == 0:
    result.info.append("all choose_n/choose_chain pools have course references")

  return result


def _worker(payload: dict[str, object]) -> FacultyParityResult:
  return _audit_faculty_parity(payload)


def _build_faculty_payloads() -> list[dict[str, object]]:
  root = wiki_root(catalog_vault_root())
  pages = load_pages_by_slug(root)
  payloads: list[dict[str, object]] = []

  for faculty_id in sorted(supported_export_faculties()):
    wiki_id = faculty_wiki_id(faculty_id)
    wiki_slugs = discover_faculty_track_slugs(pages, faculty_id)
    faculty_track_slug_set = frozenset(wiki_slugs)
    exportable_slugs = [
      slug
      for slug in wiki_slugs
      if (page := pages.get(slug)) is not None
      and should_export_degree_program(page, faculty_track_slugs=faculty_track_slug_set)
    ]
    payloads.append(
      {
        "faculty_id": faculty_id,
        "wiki_slugs": wiki_slugs,
        "exportable_slugs": exportable_slugs,
        "wiki_codes": _wiki_track_codes(pages, wiki_slugs),
      }
    )
  return payloads


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--workers",
    type=int,
    default=None,
    help=f"Process pool size (default: min(cpu, 8) = {default_worker_count(None)})",
  )
  parser.add_argument("--json", type=Path, help="Write full report JSON")
  parser.add_argument("--fail-on-gaps", action="store_true")
  args = parser.parse_args()

  faculty_ids = sorted(supported_export_faculties())
  payloads = _build_faculty_payloads()
  worker_count = default_worker_count(args.workers)
  if worker_count == 1 or len(payloads) == 1:
    results = [_worker(payload) for payload in payloads]
  else:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    results: list[FacultyParityResult | None] = [None] * len(payloads)
    with ProcessPoolExecutor(max_workers=min(worker_count, len(payloads))) as pool:
      futures = {
        pool.submit(_worker, payload): index for index, payload in enumerate(payloads)
      }
      for future in as_completed(futures):
        results[futures[future]] = future.result()
    results = [result for result in results if result is not None]

  blockers = sum(len(result.blockers) for result in results)
  warnings = sum(len(result.warnings) for result in results)
  summary = {
    "facultiesChecked": len(results),
    "facultiesPassed": sum(1 for result in results if result.ok),
    "totalBlockers": blockers,
    "totalWarnings": warnings,
    "workers": default_worker_count(args.workers),
    "faculties": [
      {
        "facultyId": result.faculty_id,
        "ok": result.ok,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "info": result.info,
      }
      for result in results
    ],
  }

  print(json.dumps(summary, indent=2, ensure_ascii=False))
  if args.json:
    args.json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {args.json}")

  if args.fail_on_gaps and blockers:
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
