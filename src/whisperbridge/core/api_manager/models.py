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

    def _get_exclude_terms(self, provider: APIProvider) -> Optional[List[str]]:
        if provider == APIProvider.OPENAI:
            return get_openai_model_excludes()
        if provider == APIProvider.GOOGLE:
            return get_google_model_excludes()
        return None

    def _is_excluded(self, model_id: str, exclude_terms: List[str]) -> bool:
        lowered = model_id.lower()
        # Check for prefix-based exclusions (starts with) and substring-based exclusions (contains)
        return any(lowered.startswith(term) or term in lowered for term in exclude_terms)

    def _sort_openai_models(self, model_ids: List[str]) -> List[str]:
        def _rank_openai(mid: str) -> tuple:
            lm = mid.lower()
            # 1. Models with "-latest" should be at the absolute end
            is_latest = 1 if "-latest" in lm else 0

            # 2. GPT-4 models (including chatgpt-4) should be second to last
            is_gpt4 = 1 if ("gpt-4" in lm or "chatgpt-4" in lm) else 0

            # 3. GPT-5 models have internal hierarchy: nano -> mini -> standard
            gpt5_rank = 3
            if lm.startswith("gpt-5"):
                if "nano" in lm:
                    gpt5_rank = 0
                elif "mini" in lm:
                    gpt5_rank = 1
                else:
                    gpt5_rank = 2

            # Calculate overall priority group
            # 0: GPT-5 (nano -> mini -> standard)
            # 1: Others
            # 2: GPT-4 (second to last)
            # 3: Latest (last)
            if is_latest:
                priority = 3
            elif is_gpt4:
                priority = 2
            elif gpt5_rank < 3:
                priority = 0
            else:
                priority = 1

            return (priority, gpt5_rank, mid)

        return sorted(model_ids, key=_rank_openai)

    def _sort_google_models(self, model_ids: List[str]) -> List[str]:
        def _rank_google(mid: str) -> tuple:
            lm = mid.lower()
            # Models with "-latest" should be at the end
            is_latest = 1 if "-latest" in lm else 0

            if "flash" in lm:
                base_rank = 0
            elif "pro" in lm:
                base_rank = 1
            else:
                base_rank = 2

            return (is_latest, base_rank, mid)

        return sorted(model_ids, key=_rank_google)

    def apply_filters(self, provider: APIProvider, model_ids: List[str]) -> List[str]:
        """
        Apply global exclusion filters and provider-specific ordering.

        Args:
            provider: The API provider.
            model_ids: List of model IDs to filter.

        Returns:
            Filtered list of model IDs.
        """
        exclude_terms = self._get_exclude_terms(provider)
        if exclude_terms is None:
            return model_ids

        filtered = [m for m in model_ids if not self._is_excluded(m, exclude_terms)]

        if provider == APIProvider.OPENAI:
            return self._sort_openai_models(filtered)
        if provider == APIProvider.GOOGLE:
            return self._sort_google_models(filtered)

        return filtered

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
                # Then apply global exclusion filters (which now also handles ranking)
                models = self.apply_filters(provider, gemini_models)
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
