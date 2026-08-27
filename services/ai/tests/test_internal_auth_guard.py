"""The token that is the only thing standing in front of this service.

`/advise` takes a `user_id` and answers with that student's transcript, GPA,
plans and remaining curriculum. It does not authenticate the student -- `api`
does that, and then calls here on their behalf. So the internal token is not a
formality: it is the whole boundary, and anything that can reach the port and
guess a `user_id` reads that student's record without it.

`require_internal_service_token` returns early when no token is configured, which
is right for a developer running the service alone and wrong everywhere else,
because an env var that fails to arrive in production removes authentication
without failing anything. These tests hold that line: unset is allowed only in
development, it is never silent, and in production it stops the service starting
-- the same shape as `api`'s `validate_production_settings`.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.dependencies.internal_auth import require_internal_service_token


class TestAConfiguredToken:
    async def test_the_right_token_is_accepted(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.dependencies.internal_auth.get_settings",
            lambda: Settings(internal_service_token="secret"),
        )
        assert await require_internal_service_token("secret") is None

    async def test_the_wrong_token_is_401(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.dependencies.internal_auth.get_settings",
            lambda: Settings(internal_service_token="secret"),
        )
        with pytest.raises(HTTPException) as caught:
            await require_internal_service_token("wrong")
        assert caught.value.status_code == 401

    async def test_no_token_at_all_is_401(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.dependencies.internal_auth.get_settings",
            lambda: Settings(internal_service_token="secret"),
        )
        with pytest.raises(HTTPException) as caught:
            await require_internal_service_token(None)
        assert caught.value.status_code == 401


class TestAnUnconfiguredToken:
    async def test_it_still_opens_the_door_in_development(self, monkeypatch) -> None:
        """Not changed. Running the service alone should not need a secret."""
        monkeypatch.setattr(
            "app.dependencies.internal_auth.get_settings",
            lambda: Settings(environment="development", internal_service_token=None),
        )
        assert await require_internal_service_token(None) is None

    async def test_it_says_so_rather_than_doing_it_quietly(
        self, monkeypatch, caplog
    ) -> None:
        """The failure mode is a missing env var in an environment nobody
        inspects. A log line is what makes it findable at all."""
        monkeypatch.setattr(
            "app.dependencies.internal_auth.get_settings",
            lambda: Settings(environment="development", internal_service_token=None),
        )
        with caplog.at_level(logging.WARNING):
            await require_internal_service_token(None)

        assert any(
            "INTERNAL_SERVICE_TOKEN" in record.message for record in caplog.records
        ), "an unauthenticated advisor should be visible in the log"


class TestProductionRefusesToRunWithoutIt:
    def test_an_unset_token_stops_the_service_starting(self) -> None:
        """`api` fails startup on an unsafe production config rather than serving
        one. This is the same rule for the same reason -- a service that starts
        without its boundary is worse than one that does not start."""
        with pytest.raises(RuntimeError) as caught:
            Settings(environment="production", internal_service_token=None).validate_production_settings()

        assert "INTERNAL_SERVICE_TOKEN" in str(caught.value)

    def test_a_blank_token_counts_as_unset(self) -> None:
        """Whitespace is what an env var set to "" in a compose file looks like."""
        with pytest.raises(RuntimeError):
            Settings(environment="production", internal_service_token="   ").validate_production_settings()

    def test_a_short_token_is_refused_like_api_refuses_it(self) -> None:
        """`api` will not start in production with fewer than 32 characters of
        this same secret. The service the secret actually protects should not be
        the lenient one."""
        with pytest.raises(RuntimeError) as caught:
            Settings(
                environment="production", internal_service_token="a-real-secret"
            ).validate_production_settings()
        assert "32" in str(caught.value)

    def test_a_configured_production_service_starts(self) -> None:
        Settings(
            environment="production", internal_service_token="x" * 32
        ).validate_production_settings()

    def test_development_is_left_alone(self) -> None:
        Settings(environment="development", internal_service_token=None).validate_production_settings()
