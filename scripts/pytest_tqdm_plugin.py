"""Pytest plugin: tqdm progress bar over collected tests (unless parent owns progress)."""

from __future__ import annotations

import os

import pytest
from tqdm import tqdm


class TqdmProgressPlugin:
    def __init__(self) -> None:
        self._bar: tqdm | None = None
        self._disabled = os.environ.get("UNIPILOT_SINGLE_PROGRESS") == "1"

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(
        self,
        session: pytest.Session,
        config: pytest.Config,
        items: list[pytest.Item],
    ) -> None:
        del session, config
        if self._disabled or not items:
            return
        self._bar = tqdm(
            total=len(items),
            desc="pytest",
            unit="test",
            dynamic_ncols=True,
            file=os.sys.stderr,
            leave=False,
            mininterval=0.1,
        )

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when != "call" or self._bar is None:
            return
        self._bar.update(1)
        if report.failed or report.skipped:
            self._bar.set_postfix_str(report.nodeid.split("::")[-1][:40], refresh=True)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        del session, exitstatus
        if self._bar is not None:
            self._bar.close()
            self._bar = None


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(TqdmProgressPlugin(), "tqdm_progress")
