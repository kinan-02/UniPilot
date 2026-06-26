#!/usr/bin/env python3
"""Sync elective_chain_pools.json contract entries from vault exports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "data-engineering"))

from app.vault.elective_chain_contract import contract_path, load_elective_chain_contract  # noqa: E402
from app.vault.export_wiki_elective_groups import collect_contract_pool_entries  # noqa: E402
from app.vault.loader import wiki_root  # noqa: E402
from app.vault.vault_export_registry import export_vault_catalog, supported_export_faculties  # noqa: E402

PRESERVE_MANUAL_CONTRACTS: frozenset[str] = frozenset({"dds", "computer-science"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--faculty",
        default="all",
        help="Faculty id or 'all' for every registered exporter.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing JSON.")
    parser.add_argument("--vault-path", type=Path, help="Optional catalog_valut wiki root.")
    args = parser.parse_args()

    faculty_ids = (
        supported_export_faculties()
        if args.faculty == "all"
        else (args.faculty.lower(),)
    )
    contract = load_elective_chain_contract()
    faculties = dict(contract.get("faculties") or {})
    total_pools = 0

    for faculty_id in faculty_ids:
        if faculty_id in PRESERVE_MANUAL_CONTRACTS and faculty_id in faculties:
            pool_count = len((faculties[faculty_id] or {}).get("pools") or [])
            print(f"{faculty_id}: skipped (manual contract preserved, {pool_count} pools)")
            total_pools += pool_count
            continue

        document, _ = export_vault_catalog(
            vault_path=args.vault_path or wiki_root(),
            faculty=faculty_id,
        )
        entries = collect_contract_pool_entries(document, faculty_id=faculty_id)
        existing = faculties.get(faculty_id, {})
        faculties[faculty_id] = {
            "deprecatedPoolSuffixes": list(existing.get("deprecatedPoolSuffixes") or []),
            "pools": entries,
        }
        total_pools += len(entries)
        print(f"{faculty_id}: {len(entries)} contracted pools")

    contract["faculties"] = faculties
    if not args.dry_run:
        contract_path().write_text(
            json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {contract_path()}")
    else:
        print("(dry run — contract file not written)")
    print(f"Total pools: {total_pools}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
