from __future__ import annotations

from app.logging_config import RedactingFilter


def test_redacts_api_keys_and_bearer_tokens() -> None:
    filt = RedactingFilter(["sk-live-super-secret"])
    assert "[REDACTED]" in filt.redact("openai_api_key=sk-live-super-secret")
    assert "super-secret" not in filt.redact("Authorization: Bearer abcdef123")
    assert "sk-live-super-secret" not in filt.redact("using sk-live-super-secret today")
    token = "123456789:AAFakeTokenValueForTestsXXXX"
    assert token not in filt.redact(f"bot {token}")


def test_numeric_arguments_still_format() -> None:
    import logging

    from app.logging_config import RedactingFilter

    record = logging.LogRecord("t", logging.INFO, __file__, 1, "Latency stt_ms=%.0f total=%d", (641.2, 3000), None)
    RedactingFilter().filter(record)
    assert record.getMessage() == "Latency stt_ms=641 total=3000"
