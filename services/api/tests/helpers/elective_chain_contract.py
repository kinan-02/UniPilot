"""Load shared elective-chain contract from the data-engineering service."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def contract_path() -> Path:
    return repo_root() / "services" / "data-engineering" / "data" / "contracts" / "elective_chain_pools.json"


def _normalize_contract(raw: dict[str, Any]) -> dict[str, Any]:
    if "faculties" in raw:
        return raw
    return {
        "version": raw.get("version", 1),
        "institutionId": raw.get("institutionId", "technion"),
        "faculties": {
            "dds": {
                "deprecatedPoolSuffixes": raw.get("deprecatedPoolSuffixes") or [],
                "pools": raw.get("pools") or [],
            }
        },
    }


@lru_cache(maxsize=1)
def load_elective_chain_contract() -> dict[str, Any]:
    return _normalize_contract(json.loads(contract_path().read_text(encoding="utf-8")))


def iter_contract_pools(*, faculty_id: str | None = None) -> list[dict[str, Any]]:
    contract = load_elective_chain_contract()
    faculties = contract.get("faculties") or {}
    if faculty_id is not None:
        section = faculties.get(faculty_id.lower())
        return list((section or {}).get("pools") or [])

    pools: list[dict[str, Any]] = []
    for section in faculties.values():
        pools.extend(section.get("pools") or [])
    return pools


def faculty_contract(faculty_id: str) -> dict[str, Any] | None:
    contract = load_elective_chain_contract()
    return (contract.get("faculties") or {}).get(faculty_id.lower())
