"""
OpenAI chat client adapter for WhisperBridge.

Provides an OpenAI-compatible interface that wraps the native OpenAI SDK
and adds provider-specific optimizations (e.g., GPT-5 reasoning parameters).
"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import openai
from loguru import logger
from openai.types.chat import ChatCompletionMessageParam

from ..core.config import get_openai_model_excludes
from ..core.model_limits import calculate_dynamic_completion_tokens, DEFAULT_MIN_OUTPUT_TOKENS

__all__ = ["OpenAIChatClientAdapter", "DEFAULT_GPT_MODELS"]

# Default GPT models list
DEFAULT_GPT_MODELS = ["gpt-5-mini", "gpt-5-nano"]


class OpenAIChatClientAdapter:
    """
    Adapter for OpenAI Chat API with OpenAI-compatible interface.

    Exposes:
      - chat.completions.create(...)
      - models.list()

    Handles OpenAI-specific optimizations like GPT-5 reasoning parameters.
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
        temperature: float = 1.0,
        max_completion_tokens: int = 256,
        **kwargs: Any,
    ) -> Any:
        """
        Handle chat completion with GPT-5 optimizations.

        Args:
            model: Model name to use.
            messages: List of message dictionaries with role and content.
            temperature: Sampling temperature.
            max_completion_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters (e.g., extra_body for GPT-5, is_vision flag).

        Returns:
            OpenAI API response object.
        """
        # Check if this is a vision request
        is_vision = kwargs.pop("is_vision", False)
        if is_vision:
            return self._create_vision(model, messages, temperature)

        # Apply GPT-5 optimizations if model starts with "gpt-5"
        if model.startswith(("gpt-5")):
            extra_body = {"reasoning_effort": "minimal", "verbosity": "low"}
            kwargs["extra_body"] = extra_body
            logger.debug(f"Using OpenAI GPT-5 optimizations: {', '.join(f'{k}={v}' for k, v in extra_body.items())}")

        # Prepare API parameters
        api_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
            **kwargs,
        }

        logger.debug(f"OpenAI API parameters: {api_params}")

        # Make the API call
        response = self._client.chat.completions.create(**api_params)
        return response

    def _create_vision(
        self,
        model: str,
        messages: List[ChatCompletionMessageParam],
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Any:
        """
        Handle vision requests with dynamic token allocation.

        Args:
            model: Model name to use.
            messages: List of message dictionaries with multimodal content.
            temperature: Sampling temperature (default 0.0 for vision).
            **kwargs: Additional parameters (is_vision flag is handled here).

        Returns:
            OpenAI API response object.
        """
        # Remove is_vision from kwargs to avoid passing to SDK
        kwargs.pop("is_vision", None)
        
        # Defensive check: validate that we have at least one image in the request
        has_image = False
        for msg in messages:
            if isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        has_image = True
                        break
            if has_image:
                break
        if not has_image:
            raise ValueError("Vision request requires at least one image part")
        
        # Dynamically calculate max_completion_tokens based on model limits
        max_completion_tokens = calculate_dynamic_completion_tokens(
            model=model,
            min_output_tokens=DEFAULT_MIN_OUTPUT_TOKENS,
            output_safety_margin=0.1
        )

        logger.debug(
            f"Vision temperature: {temperature}, "
            f"max_completion_tokens={max_completion_tokens}, model={model}"
        )

        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
        )
        return response

    def _list_models(self) -> Any:
        """
        Fetch and filter OpenAI models.

        Returns:
            SimpleNamespace with data list of model objects.
        """
        try:
            models_response = self._client.models.list()
            all_models = [model.id for model in models_response.data]
            logger.debug(f"All available models from API: {all_models}")

            # First, narrow down to chat-completion prefix patterns
            chat_models = [
                model.id
                for model in models_response.data
                if (model.id.lower().startswith("gpt-") or model.id.lower().startswith("chatgpt-"))
            ]

            # Apply global exclusion filters
            exclude_terms = get_openai_model_excludes()

            def _is_excluded(model_id: str) -> bool:
                lowered = model_id.lower()
                # Check for prefix-based exclusions (starts with) and substring-based exclusions (contains)
                return any(lowered.startswith(term) or term in lowered for term in exclude_terms)

            models = [m for m in chat_models if not _is_excluded(m)]

            logger.debug(f"Filtered OpenAI chat completion models: {models}")

            # Return SimpleNamespace with data list
            return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in models])

        except Exception as e:
            logger.error(f"Error listing OpenAI models: {e}")
            return SimpleNamespace(data=[])
