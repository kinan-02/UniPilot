"""Test-wide guards.

The only one here protects money.
"""

from __future__ import annotations

import pytest

_LIVE = "live"

_SKIP_REASON = (
    "live tests cost money and were not asked for. Run them with `pytest -m live`."
)


def _live_was_asked_for(config: pytest.Config) -> bool:
    """True only when `-m` names the live marker on THIS invocation."""
    expression = config.getoption("-m", default="") or ""
    # `-m "not live"` mentions the word and is the opposite of asking for it.
    return _LIVE in expression and "not live" not in expression.replace("  ", " ")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip `live` tests unless `-m live` asked for them, whatever else is set.

    `pytest.ini` already deselects them through `addopts`, and that is one flag
    away from being off: `-o addopts=""` is the ordinary way to drop the coverage
    options, and it drops `-m "not live"` with them. Nothing then stands between
    a routine-looking command and a bill.

    That is not hypothetical. Running `pytest tests/agent_core/facts/ -o
    addopts=""` to check one directory ran all five `test_live_*.py` files
    against `api.openai.com` for 23 minutes -- on a session whose own notes said
    this exact flag does this exact thing.

    So the rule is derived from what was ASKED FOR rather than from what happens
    to be configured. `addopts` can be cleared, overridden or edited and this
    still holds; only naming the marker gets past it, which is what the pytest.ini
    marker description has always told people to do.
    """
    if _live_was_asked_for(config):
        return

    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if _LIVE in item.keywords:
            item.add_marker(skip)
