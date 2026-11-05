"""Shared exception types. Keep these Qt-free so core and tests can use them."""


class OrionError(Exception):
    """Base application error."""


class ConfigurationError(OrionError):
    """Invalid or incomplete configuration."""


class ProviderError(OrionError):
    """LLM or external-service provider failure."""


class ProviderConfigurationError(ProviderError, ConfigurationError):
    """Provider cannot run because required settings are missing."""


class ProviderTimeoutError(ProviderError):
    """A provider request exceeded the configured timeout."""


class RateLimitError(ProviderError):
    """The provider asked us to wait. retry_after is seconds."""

    def __init__(self, message: str, retry_after: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class CancelledError(OrionError):
    """An in-flight assistant operation was cancelled."""
