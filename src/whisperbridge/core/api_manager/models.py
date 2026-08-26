"""
Model management for the API Manager package.

This module provides the ModelManager class for listing and filtering
available models from API providers, backed by an in-memory cache.
"""

import re
import threading

import openai

from typing import Dict, List, Optional, Tuple

from loguru import logger

from ..config import (
    filter_openai_model_selection,
    get_deepl_identifier,
    get_google_model_excludes,
    get_openai_model_excludes,
)
from ...providers.google_chat_adapter import GoogleChatClientAdapter
from ..provider_catalog import APIProvider
from .types import ModelSource


class ModelManager:
    """
    Manager for listing and filtering available models.

    This class handles fetching models from API providers with an
    in-memory session cache and filtering.
    """

    def __init__(self, provider_registry):
        """
        Initialize the ModelManager.

        Args:
            provider_registry: ProviderRegistry for accessing provider clients.
        """
        self._providers = provider_registry
        self._models_cache: Dict[str, List[str]] = {}
        self._cache_lock = threading.Lock()

    def get_cached_models(self, provider: str) -> Optional[List[str]]:
        """
        Return the cached model list for a provider.

        Args:
            provider: Provider identifier (e.g., "openai", "google").

        Returns:
            Cached list of model IDs, or None when missing.
        """
        with self._cache_lock:
            return self._models_cache.get(provider)

    def clear_cached_models(self, provider: Optional[str] = None) -> None:
        """
        Clear cached model lists.

        Args:
            provider: Provider identifier to clear, or None to clear all.
        """
        with self._cache_lock:
            if provider is None:
                self._models_cache.clear()
            else:
                self._models_cache.pop(provider, None)

    def cache_models_if_client_matches(self, provider: str, models: List[str], client) -> bool:
        """
        Store a model list only while `client` is still the provider's active client.

        The registry lookup and the mutation happen under one lock, so a
        concurrent reinitialize() cannot interleave between them and let an
        outdated result poison the reset cache.

        Args:
            provider: Provider identifier (e.g., "openai", "google").
            models: List of model names to cache.
            client: The client instance that produced the result.

        Returns:
            True when cached, False when credentials changed mid-request.
        """
        with self._cache_lock:
            if self._providers.get_client(provider) is not client:
                return False
            self._models_cache[provider] = models
            return True

    def clear_models_if_client_matches(self, provider: str, client) -> bool:
        """
        Clear a provider's cache entry only while `client` is still its active client.

        Args:
            provider: Provider identifier (e.g., "openai", "google").
            client: The client instance whose failed request triggered the clear.

        Returns:
            True when cleared, False when credentials changed mid-request.
        """
        with self._cache_lock:
            if self._providers.get_client(provider) is not client:
                return False
            self._models_cache.pop(provider, None)
            return True

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
        def _extract_version_parts(model_id: str) -> tuple[int, int, int]:
            match = re.match(r"^(?:gpt|chatgpt)-(\d+(?:\.\d+)*)", model_id)
            if not match:
                return (0, 0, 0)

            parts = [int(part) for part in match.group(1).split(".")]
            parts.extend([0] * (3 - len(parts)))
            return tuple(parts[:3])

        def _rank_openai(mid: str) -> tuple:
            lm = mid.lower()
            # 1. Models with "-latest" should be at the absolute end
            is_latest = 1 if "-latest" in lm else 0

            # 2. GPT-4 models (including chatgpt-4) should be second to last
            is_gpt4 = 1 if ("gpt-4" in lm or "chatgpt-4" in lm) else 0

            # 3. GPT-5 models are sorted by numeric version first (5.4 > 5.2 > 5.1 > 5),
            # then by size within the same version: nano -> mini -> standard.
            gpt5_rank = 3
            gpt5_version_key = (0, 0, 0)
            if lm.startswith(("gpt-5", "chatgpt-5")):
                version_parts = _extract_version_parts(lm)
                gpt5_version_key = tuple(-part for part in version_parts)
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

            return (priority, gpt5_version_key, gpt5_rank, mid)

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

    def _filter_models_for_selection(self, provider: APIProvider, model_ids: List[str]) -> List[str]:
        filtered = self.apply_filters(provider, model_ids)
        if provider == APIProvider.OPENAI:
            return filter_openai_model_selection(filtered)
        return filtered

    def apply_filters(self, provider: APIProvider, model_ids: List[str]) -> List[str]:
        """
        Apply global exclusion filters and provider-specific ordering.

        Args:
            provider: The API provider.
            model_ids: List of model IDs to filter.

        Returns:
            Filtered list of model IDs.
        """
        if provider == APIProvider.OPENAI:
            model_ids = [
                model_id
                for model_id in model_ids
                if model_id.lower().startswith(("gpt-", "chatgpt-"))
            ]

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
            cached_models = self.get_cached_models(provider.value)
            # Only use cache if NOT empty (unless it's DeepL which has a virtual model)
            if cached_models or provider == APIProvider.DEEPL:
                logger.debug(f"Using cached models for {provider.value}")
                # Apply global filters to cached data to ensure any newly added exclusions take effect
                filtered_models = self._filter_models_for_selection(provider, cached_models or [])
                if filtered_models:
                    return filtered_models, ModelSource.CACHE.value
                logger.info(
                    f"Cached models for {provider.value} became invalid after filtering; forcing fresh fetch."
                )
            else:
                logger.debug(f"No fresh cached models for {provider.value}, forcing fresh fetch.")

        # 2. Determine which client to use (temporary or configured)
        client = None
        source = ModelSource.API
        if temp_api_key:
            try:
                logger.debug(f"Creating temporary client for {provider.value} using provided key.")
                if provider == APIProvider.OPENAI:
                    client = openai.OpenAI(api_key=temp_api_key, timeout=10)
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
                models = self._filter_models_for_selection(
                    provider,
                    [model.id for model in models_response.data],
                )
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

            # Cache the result for successful API calls (except temp API key usage),
            # but only while the request still belongs to the current credentials
            # (a concurrent reinitialize must not let an old result poison the cache).
            # Avoid caching empty lists unless it's DeepL.
            if source != ModelSource.API_TEMP_KEY:
                if models or provider == APIProvider.DEEPL:
                    if not self.cache_models_if_client_matches(provider.value, models, client):
                        logger.debug(
                            f"Discarding model result for {provider.value} after credentials changed."
                        )
            return models, source.value

        except Exception as e:
            logger.error(f"Failed to fetch models from {provider.value}: {e}")
            # Clear cache entry for this provider to prevent caching empty/error results,
            # unless the credentials changed mid-request or this was a temp-key fetch.
            if source != ModelSource.API_TEMP_KEY:
                self.clear_models_if_client_matches(provider.value, client)
            return [], ModelSource.ERROR.value


__all__ = [
    "ModelManager",
]
