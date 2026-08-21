"""
OpenAI chat client adapter for WhisperBridge.

Provides an OpenAI-compatible interface that wraps the native OpenAI SDK.
"""

from types import SimpleNamespace
from typing import Any, List, Optional

import openai
from loguru import logger
from openai.types.chat import ChatCompletionMessageParam

from ..core.config import OPENAI_MODEL_POLICY

__all__ = ["OpenAIChatClientAdapter", "DEFAULT_GPT_MODELS"]

# Default GPT models list
# Compatibility alias derived from the central model policy.
DEFAULT_GPT_MODELS = list(OPENAI_MODEL_POLICY.fallback_models)


class OpenAIChatClientAdapter:
    """
    Adapter for OpenAI Chat API with OpenAI-compatible interface.

    Exposes:
      - chat.completions.create(...)
      - models.list()

    Passes provider-specific request parameters supplied by the API manager.
    """

    def __init__(self, api_key: str, timeout: Optional[int] = None):
        """
        Initialize the OpenAI adapter.

        Args:
            api_key: OpenAI API key.
            timeout: Optional timeout for API requests in seconds.
        """
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.models = SimpleNamespace(list=self._list_models)
        self._timeout = timeout

    def _create(
        self,
        model: str,
        messages: List[ChatCompletionMessageParam],
        max_completion_tokens: int = 256,
        **kwargs: Any,
    ) -> Any:
        """
        Handle a chat completion request.

        Args:
            model: Model name to use.
            messages: List of message dictionaries with role and content.
            max_completion_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters (e.g., GPT-5 options).

        Returns:
            OpenAI API response object.
        """
        # Prepare API parameters
        api_params = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            **kwargs,
        }

        logger.debug(f"OpenAI API parameters: {api_params}")

        # Make the API call
        response = self._client.chat.completions.create(**api_params)
        return response

    def _list_models(self) -> Any:
        """
        Fetch and normalize OpenAI models.

        Returns:
            SimpleNamespace with data list of model objects.
        """
        try:
            models_response = self._client.models.list()
            all_models = [model.id for model in models_response.data]
            logger.debug(f"All available models from API: {all_models}")

            # Selection policy belongs to ModelManager; this adapter only normalizes SDK objects.
            return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in all_models])

        except Exception as e:
            logger.error(f"Error listing OpenAI models: {e}")
            return SimpleNamespace(data=[])
