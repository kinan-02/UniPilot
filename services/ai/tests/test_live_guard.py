"""The guard that keeps `live` tests from running by accident.

`pytest.ini` deselects them via `addopts`, which is one flag from being off:
`-o addopts=""` is the ordinary way to drop the coverage options and it drops
`-m "not live"` with them. That is how five `test_live_*.py` files came to run
against `api.openai.com` for 23 minutes during this branch's work.

These run pytest in a subprocess, because the thing under test is a collection
hook and it cannot be observed from inside the session it governs.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def live_test(tmp_path: Path) -> Path:
    """A `live`-marked test that FAILS if it ever executes.

    Written into the real tests tree so the root `conftest.py` applies to it, and
    removed afterwards. A test that merely passed could not tell "skipped"
    from "ran".
    """
    path = _SERVICE_ROOT / "tests" / "_tmp_live_probe_test.py"
    path.write_text(
        textwrap.dedent(
            '''
            import pytest

            @pytest.mark.live
            def test_probe_must_not_run():
                raise AssertionError("a live test executed without being asked for")
            '''
        ).lstrip()
    )
    yield path
    path.unlink(missing_ok=True)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/_tmp_live_probe_test.py", "-q", *args],
        cwd=_SERVICE_ROOT,
        capture_output=True,
        text=True,
    )


class TestLiveTestsDoNotRunUnasked:
    def test_a_plain_run_does_not_execute_them(self, live_test: Path) -> None:
        """Deselected here rather than skipped -- `addopts` carries `-m "not
        live"`, so pytest drops it before the guard is reached. Either word means
        it did not run, which is the only thing worth asserting."""
        result = _run()
        assert "1 deselected" in result.stdout or "1 skipped" in result.stdout, (
            result.stdout[-600:]
        )
        assert "a live test executed" not in result.stdout

    def test_clearing_addopts_still_skips_them(self, live_test: Path) -> None:
        """The regression this file exists for. Before the guard, this ran the
        test and spent money."""
        result = _run("-o", "addopts=")
        assert "1 skipped" in result.stdout, result.stdout[-600:]
        assert "a live test executed" not in result.stdout

    def test_a_marker_expression_that_excludes_live_still_skips(self, live_test: Path) -> None:
        result = _run("-o", "addopts=", "-m", "not live")
        assert "executed without being asked" not in result.stdout


class TestAskingForThemStillWorks:
    def test_dash_m_live_reaches_the_test(self, live_test: Path) -> None:
        """The guard must not break the documented way in, or the next person
        works around it -- and works around the protection with it."""
        result = _run("-o", "addopts=", "-m", "live")
        # It runs, and the probe fails on purpose, which is how we know it ran.
        assert "a live test executed without being asked for" in result.stdout, (
            result.stdout[-600:]
        )
