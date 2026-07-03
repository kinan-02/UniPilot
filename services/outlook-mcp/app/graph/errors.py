"""Microsoft Graph and OAuth error types."""

from __future__ import annotations


class OutlookIntegrationError(Exception):
    code: str = "outlook_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class OutlookNotConnectedError(OutlookIntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "Outlook is not connected for this user. Connect Microsoft account first.",
            code="outlook_not_connected",
        )


class OutlookTokenExpiredError(OutlookIntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "Outlook access token expired and refresh failed. Reconnect Microsoft account.",
            code="outlook_token_expired",
        )


class OutlookConsentRequiredError(OutlookIntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "Microsoft consent is required. Reconnect and grant Mail.Read permission.",
            code="outlook_consent_required",
        )


class OutlookPermissionError(OutlookIntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "Insufficient Microsoft Graph permissions for this operation.",
            code="outlook_permission_denied",
        )


class OutlookRateLimitError(OutlookIntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "Microsoft Graph rate limit exceeded. Retry later.",
            code="outlook_rate_limited",
        )


class OutlookNotFoundError(OutlookIntegrationError):
    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found.", code="outlook_not_found")


class OutlookNetworkError(OutlookIntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "Network error while contacting Microsoft Graph.",
            code="outlook_network_error",
        )


class OutlookValidationError(OutlookIntegrationError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="outlook_validation_error")
