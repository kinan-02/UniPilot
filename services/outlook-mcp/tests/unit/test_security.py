from app.security.token_crypto import decrypt_secret, encrypt_secret
from app.tools.untrusted import UNTRUSTED_WARNING, wrap_untrusted_message, wrap_untrusted_result


def test_encrypt_decrypt_roundtrip():
    raw_key = b"test-outlook-token-encryption-key-32chars"
    ciphertext = encrypt_secret("secret-token-value", raw_key=raw_key)
    assert decrypt_secret(ciphertext, raw_key=raw_key) == "secret-token-value"
    assert "secret-token-value" not in ciphertext


def test_wrap_untrusted_result_includes_warning():
    payload = wrap_untrusted_result(data={"messages": []})
    assert payload["trusted"] is False
    assert payload["source"] == "outlook_email"
    assert payload["warning"] == UNTRUSTED_WARNING


def test_wrap_untrusted_message_marks_snippet_untrusted():
    wrapped = wrap_untrusted_message({"snippet": "Hello", "subject": "Test"})
    assert wrapped["data"]["snippet"]["trusted"] is False
    assert wrapped["warning"] == UNTRUSTED_WARNING
