"""Unit tests for auth cookie helpers."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import Response

from app.security.cookies import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)


def test_set_auth_cookies_marks_secure_in_production() -> None:
    response = Response()
    with patch("app.security.cookies._cookie_secure", return_value=True):
        set_auth_cookies(response, access_token="access", refresh_token="refresh")

    headers = response.headers.getlist("set-cookie")
    assert any(ACCESS_TOKEN_COOKIE in header and "Secure" in header for header in headers)
    assert any(REFRESH_TOKEN_COOKIE in header for header in headers)


def test_clear_auth_cookies_sets_max_age_zero() -> None:
    response = Response()
    clear_auth_cookies(response)
    headers = response.headers.getlist("set-cookie")
    assert any(ACCESS_TOKEN_COOKIE in header and "Max-Age=0" in header for header in headers)
