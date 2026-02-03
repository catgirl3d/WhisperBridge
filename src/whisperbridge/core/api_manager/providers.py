"""
Provider management for the API Manager package.

This module provides:
- APIProvider enum for supported API providers
- ProviderRegistry class for managing API provider clients
"""

from enum import Enum
from typing import Any, Dict, Optional

from loguru import logger

from ..config import validate_api_key_format
from ...providers.deepl_adapter import DeepLClientAdapter
from ...providers.google_chat_adapter import GoogleChatClientAdapter
from ...providers.openai_adapter import OpenAIChatClientAdapter


class APIProvider(str, Enum):
    """Supported API providers."""

    OPENAI = "openai"
    GOOGLE = "google"
    DEEPL = "deepl"


class ProviderRegistry:
    """
    Registry for managing API provider clients.

    This class handles initialization and management of API provider
    clients with graceful degradation for missing credentials.
    """

    def __init__(self, config_service):
        """
        Initialize the ProviderRegistry.

        Args:
            config_service: The application's configuration service.
        """
        self._clients: Dict[APIProvider, Any] = {}
        self._config = config_service

    def initialize_all(self) -> None:
        """
        Initialize all available API providers.

        This method attempts to initialize OpenAI, Google and DeepL providers
        to ensure seamless switching between them in the UI without needing
        to restart or re-save settings.
        """
        logger.debug("Initializing all available API providers.")

        # Always try to initialize all providers
        self._init_openai_provider()
        self._init_google_provider()
        self._init_deepl_provider()

        selected_provider = (self._config.get_setting("api_provider") or "").strip().lower()
        if not selected_provider:
            logger.warning("No default API provider is selected in settings.")

    def _initialize_provider(
        self,
        provider: APIProvider,
        config_key_name: str,
        key_prefix: str,
        client_factory,
        provider_name: str,
    ) -> None:
        """
        Generic method to initialize an API provider.

        Args:
            provider: The APIProvider enum member.
            config_key_name: The key for the API key in config_service.
            key_prefix: The expected prefix for the API key for validation.
            client_factory: A function that takes an api_key and timeout and returns a client.
            provider_name: The user-friendly name of the provider for logging.
        """
        api_key = self._config.get_setting(config_key_name)
        if not api_key:
            logger.warning(
                f"{provider_name} API key not configured. Translation features will be disabled."
            )
            logger.info(
                f"To enable translation with {provider_name}, set your API key in the settings."
            )
            return

        if not validate_api_key_format(api_key, provider.value):
            logger.error(f"Invalid {provider_name} API key format.")
            logger.info(
                f"Please check your {provider_name} API key format (should start with '{key_prefix}')"
            )
            return

        try:
            timeout = self._config.get_setting("api_timeout")
            client = client_factory(api_key, timeout)
            self._clients[provider] = client
            logger.info(f"{provider_name} client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize {provider_name} provider: {e}")

    def _init_openai_provider(self) -> None:
        """Initialize OpenAI provider with graceful degradation."""
        self._initialize_provider(
            provider=APIProvider.OPENAI,
            config_key_name="openai_api_key",
            key_prefix="sk-",
            client_factory=lambda key, timeout: OpenAIChatClientAdapter(api_key=key, timeout=timeout),
            provider_name="OpenAI",
        )

    def _init_google_provider(self) -> None:
        """Initialize Google Generative AI (Gemini) provider with minimal adapter."""
        self._initialize_provider(
            provider=APIProvider.GOOGLE,
            config_key_name="google_api_key",
            key_prefix="AIza",
            client_factory=lambda key, timeout: GoogleChatClientAdapter(api_key=key, timeout=timeout),
            provider_name="Google Generative AI",
        )

    def _init_deepl_provider(self) -> None:
        """Initialize DeepL translation provider (non-LLM)."""
        self._initialize_provider(
            provider=APIProvider.DEEPL,
            config_key_name="deepl_api_key",
            key_prefix="",  # DeepL keys don't have a stable prefix
            client_factory=lambda key, timeout: DeepLClientAdapter(
                api_key=key,
                timeout=timeout,
                plan=(self._config.get_setting("deepl_plan") or "free"),
            ),
            provider_name="DeepL",
        )

    def get_client(self, provider: APIProvider) -> Optional[Any]:
        """
        Get the client for a specific provider.

        Args:
            provider: The API provider to get the client for.

        Returns:
            The provider client if available, None otherwise.
        """
        return self._clients.get(provider)

    def is_provider_available(self, provider: APIProvider) -> bool:
        """
        Check if a provider is available.

        Args:
            provider: The API provider to check.

        Returns:
            True if the provider has an initialized client, False otherwise.
        """
        return provider in self._clients

    def has_any_clients(self) -> bool:
        """
        Check if any API clients are configured.

        Returns:
            True if at least one provider has an initialized client, False otherwise.
        """
        return bool(self._clients)

    def clear(self) -> None:
        """Clear all registered providers."""
        self._clients.clear()

    def get_all_providers(self) -> Dict[APIProvider, Any]:
        """
        Get all registered providers.

        Returns:
            Dictionary of provider to client mappings.
        """
        return self._clients.copy()


__all__ = [
    "APIProvider",
    "ProviderRegistry",
]
