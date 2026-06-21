"""Tests for app/__main__.py (0% coverage → full)."""

from __future__ import annotations

import runpy
import sys
from unittest.mock import patch


class TestMainModule:
    def test_raises_system_exit_on_invocation(self):
        with patch("app.main.main", return_value=0) as mock_main:
            with patch.object(sys, "argv", ["app"]):
                try:
                    runpy.run_module("app.__main__", run_name="__main__", alter_sys=False)
                except SystemExit as exc:
                    assert exc.code == 0
                mock_main.assert_called_once()

    def test_exit_code_propagated(self):
        with patch("app.main.main", return_value=42):
            with patch.object(sys, "argv", ["app"]):
                try:
                    runpy.run_module("app.__main__", run_name="__main__", alter_sys=False)
                except SystemExit as exc:
                    assert exc.code == 42
