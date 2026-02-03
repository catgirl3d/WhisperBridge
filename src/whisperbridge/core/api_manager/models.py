"""
Model management for the API Manager package.

This module provides the ModelManager class for listing and filtering
available models from API providers.
"""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from ..config import get_deepl_identifier, get_google_model_excludes, get_openai_model_excludes
from ...providers.deepl_adapter import DeepLClientAdapter
from ...providers.google_chat_adapter import GoogleChatClientAdapter
from ...providers.openai_adapter import OpenAIChatClientAdapter, DEFAULT_GPT_MODELS
from .cache import ModelCache
from .providers import APIProvider
from .types import ModelSource


class ModelManager:
    """
    Manager for listing and filtering available models.

    This class handles fetching models from API providers with caching,
    filtering, and fallback support.
    """

    def __init__(self, cache: ModelCache, config_service, provider_registry):
        """
        Initialize the ModelManager.

        Args:
            cache: ModelCache instance for caching model lists.
            config_service: The application's configuration service.
            provider_registry: ProviderRegistry for accessing provider clients.
        """
        self._cache = cache
        self._config = config_service
        self._providers = provider_registry

    def get_default_models(self) -> List[str]:
        """
        Get default model list with optional configuration override.

        Returns:
            List of default model names.
        """
        try:
            # Check for custom models in configuration
            custom_models = self._config.get_setting("default_models", use_cache=False)
            if custom_models and isinstance(custom_models, list) and ModelCache.validate_model_list(custom_models):
                logger.debug(f"Using custom default models from config: {custom_models}")
                return custom_models.copy()
        except Exception as e:
            logger.warning(f"Failed to get custom default models from config: {e}")

        # Fallback to built-in default models
        logger.debug(f"Using built-in default models: {DEFAULT_GPT_MODELS}")
        return DEFAULT_GPT_MODELS.copy()

    def get_fallback_models(self, provider: APIProvider) -> Tuple[List[str], str]:
        """
        Get fallback models with caching.

        Args:
            provider: The API provider.

        Returns:
            Tuple of (models_list, source).
        """
        if provider == APIProvider.GOOGLE:
            fallback_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        elif provider == APIProvider.DEEPL:
            fallback_models = [get_deepl_identifier()]
        else:
            fallback_models = self.get_default_models()
        self._cache.cache_models_and_persist(provider.value, fallback_models)
        return fallback_models, ModelSource.FALLBACK.value

    def apply_filters(self, provider: APIProvider, model_ids: List[str]) -> List[str]:
        """
        Apply global exclusion filters to a list of model IDs.

        Args:
            provider: The API provider.
            model_ids: List of model IDs to filter.

        Returns:
            Filtered list of model IDs.
        """
        if provider == APIProvider.OPENAI:
            exclude_terms = get_openai_model_excludes()
        elif provider == APIProvider.GOOGLE:
            exclude_terms = get_google_model_excludes()
        else:
            return model_ids

        def _is_excluded(model_id: str) -> bool:
            lowered = model_id.lower()
            # Check for prefix-based exclusions (starts with) and substring-based exclusions (contains)
            return any(lowered.startswith(term) or term in lowered for term in exclude_terms)

        return [m for m in model_ids if not _is_excluded(m)]

    def get_available_models(
        self,
        provider: APIProvider,
        temp_api_key: Optional[str] = None,
    ) -> Tuple[List[str], str]:
        """
        Get list of available models from API provider.

        Args:
            provider: The API provider to query.
            temp_api_key: If provided, use this key for a one-off request
                          instead of the configured client.

        Returns:
            Tuple of (models_list, source).
        """
        # 0. If provider is not configured and no temp key is provided, report UNCONFIGURED (ignore cache)
        if not temp_api_key:
            is_configured = self._providers.is_provider_available(provider)
            if not is_configured:
                logger.debug(f"Provider {provider.value} not configured - ignoring cache and reporting UNCONFIGURED")
                return [], ModelSource.UNCONFIGURED.value

        # 1. Check cache first, but only if not using a temporary key
        if not temp_api_key:
            cached = self._cache.get(provider.value)
            if cached:
                models, timestamp = cached
                # Only use cache if NOT empty (unless it's DeepL which has a virtual model)
                if models or provider == APIProvider.DEEPL:
                    logger.debug(f"Using cached models for {provider.value}")
                    # Apply global filters to cached data to ensure any newly added exclusions take effect
                    filtered_models = self.apply_filters(provider, models)
                    return filtered_models, ModelSource.CACHE.value
                else:
                    logger.debug(f"Cache for {provider.value} is empty, forcing fresh fetch.")

        # 2. Determine which client to use (temporary or configured)
        client = None
        source = ModelSource.API
        if temp_api_key:
            try:
                logger.debug(f"Creating temporary client for {provider.value} using provided key.")
                if provider == APIProvider.OPENAI:
                    client = OpenAIChatClientAdapter(api_key=temp_api_key, timeout=10)
                elif provider == APIProvider.GOOGLE:
                    client = GoogleChatClientAdapter(api_key=temp_api_key, timeout=10)
                source = ModelSource.API_TEMP_KEY
            except Exception as e:
                logger.error(f"Failed to create temporary client: {e}")
                return [], ModelSource.ERROR.value
        else:
            client = self._providers.get_client(provider)

        # 3. If no client could be determined, exit
        if not client:
            logger.debug(f"Provider {provider.value} not configured and no valid temp key provided.")
            return [], ModelSource.UNCONFIGURED.value

        # 4. Now, fetch models using the determined client
        try:
            if provider == APIProvider.OPENAI:
                models_response = client.models.list()
                models = [model.id for model in models_response.data]
                logger.debug(f"Filtered OpenAI chat completion models: {models}")

            elif provider == APIProvider.GOOGLE:
                models_response = client.models.list()
                all_models = [m.id for m in models_response.data]
                logger.debug(f"All available GOOGLE models from API: {all_models}")

                # First, narrow down to Gemini prefix patterns
                gemini_models = [
                    m.id for m in models_response.data
                    if m.id.lower().startswith("gemini-")
                ]
                # Then apply global exclusion filters
                models = self.apply_filters(provider, gemini_models)
                def _rank(mid: str) -> tuple:
                    lm = mid.lower()
                    if "flash-8b" in lm: return (0, mid)
                    if "flash" in lm: return (1, mid)
                    if "pro" in lm: return (2, mid)
                    return (3, mid)
                models.sort(key=_rank)
                logger.debug(f"Filtered Gemini chat models: {models}")

            elif provider == APIProvider.DEEPL:
                models_response = client.models.list()
                all_models = [m.id for m in models_response.data]
                logger.debug(f"All available DEEPL models from API: {all_models}")
                models = all_models or [get_deepl_identifier()]
            else:
                return [], ModelSource.ERROR.value

            # Cache the result for successful API calls (except temp API key usage)
            # Avoid caching empty lists unless it's DeepL
            if source != ModelSource.API_TEMP_KEY:
                if models or provider == APIProvider.DEEPL:
                    self._cache.cache_models_and_persist(provider.value, models)
            return models, source.value

        except Exception as e:
            logger.error(f"Failed to fetch models from {provider.value}: {e}")
            # Clear cache entry for this provider to prevent caching empty/error results
            self._cache.clear(provider.value)
            return [], ModelSource.ERROR.value


__all__ = [
    "ModelManager",
]
