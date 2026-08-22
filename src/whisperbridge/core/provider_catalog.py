"""Supported API provider catalog."""

from enum import Enum


class APIProvider(str, Enum):
    """Supported API providers."""

    OPENAI = "openai"
    GOOGLE = "google"
    DEEPL = "deepl"


def get_supported_provider_values() -> list[str]:
    """Return provider values in their user-facing order."""
    return [provider.value for provider in APIProvider]


__all__ = ["APIProvider", "get_supported_provider_values"]
