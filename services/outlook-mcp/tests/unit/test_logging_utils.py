import logging

from app.logging_utils import log_tool_call, sanitize_log_fields


def test_sanitize_log_fields_redacts_tokens_and_bodies():
    sanitized = sanitize_log_fields(
        {
            "accessToken": "abc",
            "refresh_token": "def",
            "bodyPreview": "secret email body",
            "messageId": "msg-1",
        }
    )
    assert sanitized["accessToken"] == "[REDACTED]"
    assert sanitized["refresh_token"] == "[REDACTED]"
    assert sanitized["bodyPreview"] == "[REDACTED]"
    assert sanitized["messageId"] == "msg-1"


def test_log_tool_call_does_not_log_sensitive_values(caplog):
    logger = logging.getLogger("test.outlook")
    with caplog.at_level(logging.INFO):
        log_tool_call(
            logger,
            tool_name="outlook_get_message",
            user_id="507f1f77bcf86cd799439011",
            extra={"accessToken": "super-secret", "messageId": "abc"},
        )
    joined = " ".join(record.message for record in caplog.records)
    assert "super-secret" not in joined
