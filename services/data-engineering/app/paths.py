"""Filesystem paths for the data-engineering service."""

from __future__ import annotations

from pathlib import Path


def service_root() -> Path:
    return Path(__file__).resolve().parents[1]


def catalog_vault_root() -> Path:
    return service_root() / "data" / "catalog_valut"


def catalog_vault_wiki_root() -> Path:
    return catalog_vault_root() / "wiki"


def default_catalog_export_dir() -> Path:
    return service_root() / "data" / "generated" / "technion" / "catalog"


def default_catalog_reviewed_path() -> Path:
    return default_catalog_export_dir() / "catalog_reviewed.json"


def default_readiness_path() -> Path:
    return default_catalog_export_dir() / "catalog_phase8_readiness_check.json"
