"""Rotating file logs with secret redaction."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from typing import Iterable

from app.config import AppConfig
from app.paths import logs_dir

_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key\s*[=:]\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(authorization\s*[=:]\s*bearer\s+)(\S+)", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9]{10,})"),
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"),
)


class RedactingFilter(logging.Filter):
    def __init__(self, extra_secrets: Iterable[str] | None = None) -> None:
        super().__init__()
        self._extra = [secret for secret in (extra_secrets or []) if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {key: self._arg(value) for key, value in record.args.items()}
            else:
                record.args = tuple(self._arg(arg) for arg in record.args)
        return True

    def _arg(self, value: object) -> object:
        """Redact without turning numbers into text, which would break %d and %.0f."""
        text = str(value)
        clean = self.redact(text)
        if isinstance(value, str) or clean != text:
            return clean
        return value

    def redact(self, text: str) -> str:
        redacted = text
        for secret in self._extra:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        for pattern in _SECRET_PATTERNS:
            if pattern.groups == 2:
                redacted = pattern.sub(r"\1[REDACTED]", redacted)
            else:
                redacted = pattern.sub("[REDACTED]", redacted)
        return redacted


def setup_logging(config: AppConfig) -> logging.Logger:
    logger = logging.getLogger("orion")
    logger.setLevel(getattr(logging, config.log_level, logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    secrets = [config.openai_api_key, config.weather_api_key, config.telegram_bot_token]
    redactor = RedactingFilter(secrets)

    file_handler = RotatingFileHandler(
        logs_dir() / "orion.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(redactor)

    logger.addHandler(file_handler)
    logger.addHandler(console)
    logger.debug("Logging initialized")
    return logger
