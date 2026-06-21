"""Tests for smaller gaps: app/paths.py, app/logging_config.py, app/utils/*."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# app/paths.py
# ---------------------------------------------------------------------------

class TestPaths:
    def test_service_root_is_directory(self):
        from app.paths import service_root
        root = service_root()
        assert isinstance(root, Path)
        assert root.is_dir()

    def test_catalog_vault_root(self):
        from app.paths import catalog_vault_root
        p = catalog_vault_root()
        assert isinstance(p, Path)
        assert "catalog_valut" in str(p)

    def test_catalog_vault_wiki_root(self):
        from app.paths import catalog_vault_wiki_root
        p = catalog_vault_wiki_root()
        assert isinstance(p, Path)
        assert "wiki" in str(p)

    def test_default_catalog_export_dir(self):
        from app.paths import default_catalog_export_dir
        p = default_catalog_export_dir()
        assert isinstance(p, Path)
        assert "generated" in str(p)

    def test_default_catalog_reviewed_path(self):
        from app.paths import default_catalog_reviewed_path
        p = default_catalog_reviewed_path()
        assert isinstance(p, Path)
        assert p.suffix == ".json"

    def test_default_readiness_path(self):
        from app.paths import default_readiness_path
        p = default_readiness_path()
        assert isinstance(p, Path)
        assert p.suffix == ".json"


# ---------------------------------------------------------------------------
# app/logging_config.py
# ---------------------------------------------------------------------------

class TestLoggingConfig:
    def test_configure_logging_does_not_raise(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        get_settings.cache_clear()

        from app.logging_config import configure_logging
        configure_logging()  # must not raise

        get_settings.cache_clear()

    def test_configure_logging_with_info_level(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        get_settings.cache_clear()

        from app.logging_config import configure_logging
        configure_logging()  # must not raise
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# app/utils/course_numbers.py
# ---------------------------------------------------------------------------

class TestCourseNumbers:
    def test_normalize_8_digit_number_starting_with_0(self):
        from app.utils.course_numbers import normalize_course_number
        assert normalize_course_number("01234567") == "01234567"

    def test_pads_7_digit_number_with_leading_zero(self):
        from app.utils.course_numbers import normalize_course_number
        result = normalize_course_number("1234567")
        assert result is not None
        assert result.startswith("0")

    def test_returns_none_for_invalid(self):
        from app.utils.course_numbers import normalize_course_number
        assert normalize_course_number("abc") is None

    def test_returns_none_for_empty(self):
        from app.utils.course_numbers import normalize_course_number
        assert normalize_course_number("") is None

    def test_strips_whitespace(self):
        from app.utils.course_numbers import normalize_course_number
        result = normalize_course_number("  01234567  ")
        assert result == "01234567"

    def test_9_digit_number_invalid(self):
        from app.utils.course_numbers import normalize_course_number
        assert normalize_course_number("012345678") is None


# ---------------------------------------------------------------------------
# app/utils/hebrew_rtl.py
# ---------------------------------------------------------------------------

class TestHebrewRtl:
    def test_hebrew_letter_ratio_high_for_hebrew(self):
        from app.utils.hebrew_rtl import hebrew_letter_ratio
        ratio = hebrew_letter_ratio("שלום עולם")
        assert ratio > 0.5

    def test_hebrew_letter_ratio_zero_for_latin(self):
        from app.utils.hebrew_rtl import hebrew_letter_ratio
        ratio = hebrew_letter_ratio("Hello world")
        assert ratio == 0.0

    def test_hebrew_letter_ratio_zero_for_empty(self):
        from app.utils.hebrew_rtl import hebrew_letter_ratio
        assert hebrew_letter_ratio("") == 0.0

    def test_normalize_whitespace_collapses_spaces(self):
        from app.utils.hebrew_rtl import normalize_whitespace
        result = normalize_whitespace("hello   world")
        assert result == "hello world"

    def test_normalize_whitespace_strips_blank_lines(self):
        from app.utils.hebrew_rtl import normalize_whitespace
        result = normalize_whitespace("line1\n\n\n\nline2")
        assert "\n\n\n" not in result

    def test_normalize_hebrew_punctuation(self):
        from app.utils.hebrew_rtl import normalize_hebrew_punctuation
        result = normalize_hebrew_punctuation("hello – world")
        assert "–" not in result
        assert "-" in result

    def test_should_reverse_line_empty(self):
        from app.utils.hebrew_rtl import should_reverse_line
        assert should_reverse_line("") is False

    def test_process_hebrew_text_returns_tuple(self):
        from app.utils.hebrew_rtl import process_hebrew_text
        raw, processed = process_hebrew_text("שלום")
        assert raw == "שלום"
        assert isinstance(processed, str)
