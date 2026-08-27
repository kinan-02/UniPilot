"""Unit tests for `app.config.Settings`'s academic-data path resolution.

Found necessary the hard way: every live-eval run this session (executed
directly via pytest, not through Docker) silently had zero working academic
data, since `academic_wiki_path`/`academic_technion_raw_dir` default to
Docker-only `/app/...` paths with no local-dev fallback. Every course/wiki
lookup failed with `academic_graph_unavailable` the entire time, not
because the referenced course/track genuinely couldn't be found.
"""

from __future__ import annotations

import app.config as config_module
from app.config import Settings


def test_resolved_technion_raw_dir_falls_back_to_local_dir_when_configured_path_is_missing(
    tmp_path, monkeypatch
):
    local_dir = tmp_path / "local-technion-raw"
    local_dir.mkdir()
    monkeypatch.setattr(config_module, "_LOCAL_ACADEMIC_TECHNION_RAW_DIR", local_dir)

    settings = Settings(academic_technion_raw_dir="/app/data/raw/technion", _env_file=None)

    assert settings.resolved_technion_raw_dir() == str(local_dir)


def test_resolved_technion_raw_dir_keeps_configured_path_when_it_actually_exists(tmp_path, monkeypatch):
    real_dir = tmp_path / "real-technion-raw"
    real_dir.mkdir()
    local_dir = tmp_path / "local-technion-raw"
    local_dir.mkdir()
    monkeypatch.setattr(config_module, "_LOCAL_ACADEMIC_TECHNION_RAW_DIR", local_dir)

    settings = Settings(academic_technion_raw_dir=str(real_dir), _env_file=None)

    assert settings.resolved_technion_raw_dir() == str(real_dir)


def test_resolved_academic_wiki_path_falls_back_to_local_dir_when_configured_path_is_missing(
    tmp_path, monkeypatch
):
    local_dir = tmp_path / "local-wiki"
    local_dir.mkdir()
    monkeypatch.setattr(config_module, "_LOCAL_ACADEMIC_WIKI_PATH", local_dir)

    settings = Settings(academic_wiki_path="/app/data/academic/wiki", _env_file=None)

    assert settings.resolved_academic_wiki_path() == str(local_dir)


def test_resolved_academic_wiki_path_keeps_configured_path_when_it_actually_exists(tmp_path, monkeypatch):
    real_dir = tmp_path / "real-wiki"
    real_dir.mkdir()
    local_dir = tmp_path / "local-wiki"
    local_dir.mkdir()
    monkeypatch.setattr(config_module, "_LOCAL_ACADEMIC_WIKI_PATH", local_dir)

    settings = Settings(academic_wiki_path=str(real_dir), _env_file=None)

    assert settings.resolved_academic_wiki_path() == str(real_dir)


def test_resolved_technion_raw_dir_never_falls_back_when_no_local_dir_exists(tmp_path, monkeypatch):
    """The fallback must never fire silently when nothing real is actually
    there to fall back to -- stays on the configured (possibly-broken)
    path rather than swapping to a nonexistent one."""
    missing_local_dir = tmp_path / "does-not-exist"
    monkeypatch.setattr(config_module, "_LOCAL_ACADEMIC_TECHNION_RAW_DIR", missing_local_dir)

    settings = Settings(academic_technion_raw_dir="/app/data/raw/technion", _env_file=None)

    assert settings.resolved_technion_raw_dir() == "/app/data/raw/technion"
