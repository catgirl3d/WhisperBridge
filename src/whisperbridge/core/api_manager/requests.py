"""
Request building utilities for the API Manager package.

This module provides:
- Temperature support helpers for model-specific temperature handling
- RequestBuilder class for building API request parameters
"""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from ..model_limits import calculate_dynamic_completion_tokens, DEFAULT_MIN_OUTPUT_TOKENS


def model_supports_temperature(model: str) -> bool:
    """
    Check if the model supports custom temperature values.

    Reasoning models (o1, o3, GPT-5 reasoning) only support temperature=1.0.
    Other models support temperature in range [0.0, 2.0].

    Args:
        model: Model name (e.g., "gpt-5-nano", "o1-preview", "gpt-4o-mini")

    Returns:
        True if model supports custom temperature, False otherwise.
    """
    model_lower = model.lower()

    # Models that only support temperature=1.0 (reasoning models)
    restricted_prefixes = [
        "o1-",      # o1-preview, o1-mini
        "o3-",      # o3-mini, o3-preview (future models)
        "gpt-5",    # GPT-5 models with reasoning_effort parameter
    ]

    # Check if model starts with any restricted prefix
    for prefix in restricted_prefixes:
        if model_lower.startswith(prefix):
            logger.debug(f"Model '{model}' is restricted (prefix: {prefix}), temperature must be 1.0")
            return False

    return True


def adjust_temperature_for_model(model: str, temperature: float) -> float:
    """
    Adjust temperature value based on model capabilities.

    If the model doesn't support custom temperature, forces temperature=1.0.
    Logs the adjustment if it occurs.

    Args:
        model: Model name to check
        temperature: Desired temperature value

    Returns:
        Adjusted temperature (1.0 for restricted models, otherwise original value)
    """
    if not model_supports_temperature(model):
        if temperature != 1.0:
            logger.info(
                f"Model '{model}' does not support custom temperature. "
                f"Overriding {temperature} -> 1.0"
            )
        return 1.0
    return temperature


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

    def resolve_llm_temperature_and_limits(
        self,
        *,
        model: str,
        temperature: Optional[float],
        temperature_setting_key: str,
        temperature_default: float,
        log_label: str,
    ) -> Tuple[float, int]:
        """
        Resolve LLM temperature and max completion tokens for a request.

        Args:
            model: Model name.
            temperature: Optional temperature override.
            temperature_setting_key: Config key for temperature setting.
            temperature_default: Default temperature value.
            log_label: Label for logging (e.g., "Translation", "Vision").

        Returns:
            Tuple of (resolved_temperature, max_completion_tokens).
        """
        if temperature is None:
            try:
                val = self._config.get_setting(temperature_setting_key)
                resolved_temp = round(float(val if val is not None else temperature_default), 2)
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse {log_label.lower()} temperature from config, using default {temperature_default}. Error: {e}"
                )
                resolved_temp = temperature_default
        else:
            try:
                resolved_temp = round(float(temperature), 2)
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse provided temperature '{temperature}', using default {temperature_default}. Error: {e}"
                )
                resolved_temp = temperature_default

        resolved_temp = adjust_temperature_for_model(model, resolved_temp)

        max_completion_tokens = calculate_dynamic_completion_tokens(
            model=model,
            min_output_tokens=DEFAULT_MIN_OUTPUT_TOKENS,
            output_safety_margin=0.1
        )

        logger.debug(f"{log_label} temperature: {resolved_temp}, max_completion_tokens={max_completion_tokens}")
        return resolved_temp, max_completion_tokens

    def build_llm_params(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        temperature_setting_key: str,
        temperature_default: float,
        log_label: str,
    ) -> Dict[str, Any]:
        """
        Build API params for LLM providers with normalized temperature and limits.

        Args:
            model: Model name.
            messages: List of messages for the chat completion.
            temperature: Optional temperature override.
            temperature_setting_key: Config key for temperature setting.
            temperature_default: Default temperature value.
            log_label: Label for logging.

        Returns:
            Dictionary of API parameters.
        """
        resolved_temp, max_completion_tokens = self.resolve_llm_temperature_and_limits(
            model=model,
            temperature=temperature,
            temperature_setting_key=temperature_setting_key,
            temperature_default=temperature_default,
            log_label=log_label,
        )
        return {
            "model": model,
            "messages": messages,
            "temperature": resolved_temp,
            "max_completion_tokens": max_completion_tokens,
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
    "model_supports_temperature",
    "adjust_temperature_for_model",
    "RequestBuilder",
]
