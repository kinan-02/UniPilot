#!/usr/bin/env python3
"""Verify elective chain pools against the shared per-faculty contract (export JSON or live Mongo)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "data-engineering"))

from app.vault.elective_chain_contract import (  # noqa: E402
    contracted_faculty_ids,
    iter_contract_pools,
    load_elective_chain_contract,
    validate_elective_chain_export,
)
from app.vault.loader import wiki_root  # noqa: E402
from app.vault.vault_export_registry import export_vault_catalog, supported_export_faculties  # noqa: E402


def verify_export(vault_path: Path | None, faculty: str) -> list[str]:
    document, _ = export_vault_catalog(vault_path=vault_path or wiki_root(), faculty=faculty)
    return validate_elective_chain_export(document, faculty_id=faculty)


def verify_mongo(mongo_uri: str, db_name: str, *, faculty: str | None) -> list[str]:
    from pymongo import MongoClient

    client = MongoClient(mongo_uri)
    db = client[db_name]
    violations: list[str] = []

    faculty_ids = [faculty] if faculty else list(contracted_faculty_ids())
    for faculty_id in faculty_ids:
        for entry in iter_contract_pools(faculty_id=faculty_id):
            group_id = f"{entry['programCode']}:{entry['suffix']}"
            doc = db.catalog_rules.find_one({"requirementGroupId": group_id})
            if doc is None:
                violations.append(f"mongo missing catalog_rules document for {group_id}")
                continue
            refs = doc.get("courseReferences") or []
            if len(refs) < entry["minCourseRefs"] or len(refs) > entry["maxCourseRefs"]:
                violations.append(
                    f"mongo {group_id} has {len(refs)} refs (expected "
                    f"{entry['minCourseRefs']}-{entry['maxCourseRefs']})"
                )
            if entry.get("requiresCatalogDescription") and not doc.get("catalogDescription"):
                violations.append(f"mongo {group_id} missing catalogDescription")

        section = load_elective_chain_contract().get("faculties", {}).get(faculty_id, {})
        for suffix in section.get("deprecatedPoolSuffixes") or []:
            if db.catalog_rules.find_one({"requirementGroupId": {"$regex": f":{suffix}$"}}):
                violations.append(f"mongo still contains deprecated pool suffix {suffix}")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--faculty",
        default="dds",
        help=(
            "Faculty id to verify (default: dds). Use 'all' to verify every contracted faculty "
            f"with a registered exporter. Exporters: {', '.join(supported_export_faculties())}"
        ),
    )
    parser.add_argument(
        "--mongo-uri",
        help="Optional Mongo URI to verify production catalog_rules documents.",
    )
    parser.add_argument("--db", default="unipilot_python", help="Mongo database name.")
    parser.add_argument(
        "--vault-path",
        type=Path,
        help="Optional catalog_valut root (defaults to repo vault).",
    )
    args = parser.parse_args()

    faculty_arg = args.faculty.lower()
    if faculty_arg == "all":
        export_faculties = [
            faculty_id
            for faculty_id in contracted_faculty_ids()
            if faculty_id in supported_export_faculties()
        ]
    else:
        export_faculties = [faculty_arg]

    violations: list[str] = []
    for faculty_id in export_faculties:
        violations.extend(verify_export(args.vault_path, faculty_id))

    if args.mongo_uri:
        mongo_faculty = None if faculty_arg == "all" else faculty_arg
        violations.extend(verify_mongo(args.mongo_uri, args.db, faculty=mongo_faculty))

    if violations:
        print(json.dumps({"status": "fail", "violations": violations}, indent=2))
        return 1

    pools_checked = sum(len(iter_contract_pools(faculty_id=f)) for f in export_faculties)
    print(
        json.dumps(
            {
                "status": "ok",
                "facultiesChecked": export_faculties,
                "poolsChecked": pools_checked,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
