"""Single in-place progress bar for RAG fine-tuning pipelines."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Protocol

ProgressCallback = Callable[[str], None]


class ProgressReporter(Protocol):
    def set_phase(self, phase: str) -> None: ...

    def advance(self, n: int = 1) -> None: ...

    def close(self) -> None: ...


class SingleBarProgress:
    """One tqdm bar that updates in place for an entire run."""

    def __init__(
        self,
        total: int,
        *,
        desc: str = "RAG fine-tuning",
        disable: bool = False,
    ) -> None:
        from tqdm import tqdm

        self._bar = tqdm(
            total=max(1, int(total)),
            desc=desc,
            unit="step",
            dynamic_ncols=True,
            leave=True,
            file=sys.stderr,
            mininterval=0.2,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        )
        if disable:
            self._bar.disable = True

    def set_phase(self, phase: str) -> None:
        self._bar.set_description_str(phase, refresh=False)
        self._bar.refresh()

    def set_total(self, total: int) -> None:
        self._bar.total = max(1, int(total))
        self._bar.refresh()

    def advance(self, n: int = 1) -> None:
        self._bar.update(n)

    def close(self) -> None:
        self._bar.close()

    @staticmethod
    def write(message: str) -> None:
        from tqdm import tqdm

        tqdm.write(message)


class NullProgress:
    def set_phase(self, phase: str) -> None:
        return None

    def advance(self, n: int = 1) -> None:
        return None

    def close(self) -> None:
        return None

    @staticmethod
    def write(message: str) -> None:
        print(message)
