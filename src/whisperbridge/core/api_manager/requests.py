"""
Request building utilities for the API Manager package.

This module provides request parameter builders for the API Manager package.
"""

from typing import Any, Dict, List, Optional

from ..model_limits import get_model_max_completion_tokens


class RequestBuilder:
    """
    Builder for API request parameters.

    This class provides methods to build normalized request parameters
    for different API providers (LLM and DeepL).
    """

    def __init__(self, config_service):
        """
        Initialize the RequestBuilder.

        Args:
            config_service: The application's configuration service.
        """
        self._config = config_service

    def build_llm_params(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build API params for LLM providers with model-specific token limits.

        Args:
            model: Model name.
            messages: List of messages for the chat completion.
        Returns:
            Dictionary of API parameters.
        """
        return {
            "model": model,
            "messages": messages,
            "max_completion_tokens": get_model_max_completion_tokens(model),
        }

    def build_deepl_params(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        api_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build API params for DeepL translation requests.

        Args:
            model: Model name.
            messages: List of messages for the translation.
            api_kwargs: Additional provider-specific kwargs (e.g., target_lang/source_lang).

        Returns:
            Dictionary of API parameters.
        """
        api_params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        for key, value in (api_kwargs or {}).items():
            if value is not None:
                api_params[key] = value
        return api_params


__all__ = [
    "RequestBuilder",
]
