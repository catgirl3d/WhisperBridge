"""
API Manager orchestrator for WhisperBridge.

This module provides the APIManager class which coordinates all components
of the API management system.
"""

import threading
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import ensure_config_dir, get_deepl_identifier
from ..model_limits import get_model_max_completion_tokens
from ...services.config_service import ConfigService
from .cache import ModelCache
from .errors import APIError, APIErrorType, RetryableAPIError, classify_error, log_network_diagnostics, requires_initialization
from .models import ModelManager
from .providers import APIProvider, ProviderRegistry


class APIManager:
    """
    Centralized API manager for handling authentication and requests.

    This class acts as a thin orchestrator that delegates to specialized
    components for provider management, caching, and model listing.
    """

    def __init__(self, config_service: ConfigService):
        """
        Initialize the APIManager.

        Args:
            config_service: The application's configuration service.
        """
        self.config_service = config_service
        self._lock = threading.RLock()
        self._is_initialized = False
        self._diag_logged = False  # log network/SSL diagnostics once

        # Initialize components
        config_dir = ensure_config_dir()
        self._cache = ModelCache(config_dir)
        self._providers = ProviderRegistry(config_service)
        self._model_manager = ModelManager(self._cache, config_service, self._providers)

    def initialize(self) -> bool:
        """
        Initialize API manager with configured providers.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        with self._lock:
            success = False
            try:
                self._providers.initialize_all()
                success = True
            except Exception as e:
                logger.error(f"Failed to initialize API providers: {e}")

            # Always finalize to allow offline/partial functionality
            # This sets _is_initialized to True and loads the cache
            self._finalize_initialization()
            return success

    def reinitialize(self) -> bool:
        """
        Reinitialize API manager using the latest configuration values.

        Clears existing clients, then re-runs the standard initialization workflow
        so the manager picks up refreshed credentials or provider settings. Model
        cache is cleared to ensure fresh API calls with new credentials.

        Returns:
            True if reinitialization succeeded, False otherwise.
        """
        logger.info("Reinitializing API manager with updated settings")
        with self._lock:
            self._providers.clear()
            self._cache.clear(delete_persisted=True)
            self._is_initialized = False

        return self.initialize()

    def _finalize_initialization(self) -> None:
        """Finalize initialization with consistent status setting and cache loading."""
        # Allow initialization even without API clients
        # The app can still run OCR and other features
        self._is_initialized = True

        # Load any persistent model cache from disk so first-run UI can use it
        self._cache.initialize_safely()

        if self._providers.has_any_clients():
            logger.info("API manager initialized successfully with clients")
        else:
            logger.info("API manager initialized (no API clients - translation features disabled)")

    def is_initialized(self) -> bool:
        """Check if API manager is initialized."""
        return self._is_initialized

    def has_clients(self) -> bool:
        """Check if any API clients are configured."""
        return self._providers.has_any_clients()

    def _resolve_provider(self, provider_name: Optional[str] = None) -> APIProvider:
        """
        Resolve and validate the configured API provider.

        Args:
            provider_name: Optional provider name override.

        Returns:
            The resolved APIProvider.

        Raises:
            RuntimeError: If provider is invalid or not available.
        """
        resolved_name = (provider_name or self.config_service.get_setting("api_provider") or "openai").strip().lower()
        try:
            selected_provider = APIProvider(resolved_name)
        except ValueError:
            raise RuntimeError(f"Invalid API provider '{resolved_name}' configured in settings.")

        if not self._providers.is_provider_available(selected_provider):
            raise RuntimeError(
                f"The configured API provider '{resolved_name}' is not available. "
                "Please check your API key in the settings."
            )

        return selected_provider

    def _resolve_model(self, model_hint: Optional[str], provider: APIProvider, *, missing_message: str) -> str:
        """
        Resolve model name, applying provider-specific defaults if needed.

        Args:
            model_hint: The model hint from the user.
            provider: The API provider.
            missing_message: Error message if model is missing.

        Returns:
            The resolved model name.

        Raises:
            ValueError: If model is required but not provided.
        """
        final_model = (model_hint or "").strip()
        if provider == APIProvider.DEEPL:
            return final_model or get_deepl_identifier()
        if not final_model:
            raise ValueError(missing_message)
        return final_model

    def _build_llm_params(self, model: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build common parameters for an LLM chat-completion request."""
        return {
            "model": model,
            "messages": messages,
            "max_completion_tokens": get_model_max_completion_tokens(model),
        }

    @requires_initialization
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(RetryableAPIError),
    )
    def make_request_sync(self, provider: APIProvider, **kwargs) -> Any:
        """
        Make API request with retry logic.

        Args:
            provider: The API provider to use.
            **kwargs: Additional keyword arguments for the API request.

        Returns:
            The API response.

        Raises:
            ValueError: If provider is not configured.
            Exception: For non-retryable errors.
        """
        if "temperature" in kwargs:
            raise TypeError("temperature is not a supported API request parameter")

        client = self._providers.get_client(provider)
        if not client:
            raise ValueError(f"Provider {provider.value} not configured. Please set up your API key in settings.")

        try:
            logger.debug(f"Making API request to provider '{provider.value}' with args: {kwargs}")
            if not self._diag_logged:
                log_network_diagnostics()
                self._diag_logged = True
            start_time = time.time()
            response = client.chat.completions.create(**kwargs)
            request_time = time.time() - start_time
            logger.debug(f"Raw API response: {response}")

            logger.debug(f"API request completed in {request_time:.2f}s")
            return response

        except Exception as e:
            api_error = classify_error(e, provider.value)

            logger.error(f"API request failed: {api_error.error_type.value} - {api_error.message}")

            # Check if the error is retryable based on its type
            if api_error.error_type in [
                APIErrorType.RATE_LIMIT,
                APIErrorType.NETWORK,
                APIErrorType.TIMEOUT,
                APIErrorType.SERVER_ERROR,
            ]:
                # Wrap in custom exception to trigger tenacity retry
                raise RetryableAPIError(f"Retryable error occurred: {api_error.message}") from e

            # For non-retryable errors, re-raise the original exception
            raise e

    @requires_initialization
    def make_translation_request(
        self,
        messages: List[Dict[str, Any]],
        model_hint: Optional[str] = None,
        **api_kwargs
    ) -> tuple[Any, str]:
        """
        Makes a translation request using the configured provider.

        This method encapsulates the logic for:
        1. Selecting the provider specified in the settings.
        2. Applying provider-specific optimizations (e.g., for OpenAI).
        3. Calling the core `make_request_sync` method.

        Args:
            messages: A list of messages for the chat completion.
            model_hint: The model name to use for the request.
            api_kwargs: Additional provider-specific kwargs (e.g., target_lang/source_lang for DeepL).

        Returns:
            A tuple containing the API response and the model name used.
        """
        # 1. Select the configured provider
        selected_provider = self._resolve_provider()

        # 2. Resolve model (provider-specific defaults)
        final_model = self._resolve_model(
            model_hint,
            selected_provider,
            missing_message="Model name must be provided for the translation request.",
        )

        if selected_provider == APIProvider.DEEPL:
            api_params = {"model": final_model, "messages": messages}
            api_params.update(
                {key: value for key, value in api_kwargs.items() if value is not None}
            )
            logger.debug(f"Final API parameters for {selected_provider.value}: {api_params}")
            response = self.make_request_sync(selected_provider, **api_params)
            return response, final_model

        # 3. Prepare API call parameters for LLM providers
        api_params = self._build_llm_params(final_model, messages)

        # Reasoning effort is intentionally limited to text translation;
        # vision/OCR requests use make_vision_request and do not inherit it.
        if selected_provider == APIProvider.OPENAI:
            reasoning_effort = self.config_service.get_setting("openai_reasoning_effort") or "not_set"
            if reasoning_effort != "not_set":
                api_params["reasoning_effort"] = reasoning_effort

        logger.debug(f"Final API parameters for {selected_provider.value}: {api_params}")

        # 4. Make the API call
        response = self.make_request_sync(selected_provider, **api_params)

        return response, final_model

    @requires_initialization
    def make_vision_request(self, messages: List[Dict[str, Any]], model_hint: str) -> tuple[Any, str]:
        """
        Makes a vision request using the configured provider for multimodal content.

        This method handles vision-capable providers (OpenAI, Google) and normalizes
        responses to an OpenAI-like structure. For non-vision providers, raises an error.

        Args:
            messages: OpenAI-style message list with multimodal content.
            model_hint: Suggested model name (e.g., settings.openai_vision_model or settings.google_vision_model).

        Returns:
            Tuple of (response_object, final_model_str) where response_object has OpenAI-like structure.

        Raises:
            ValueError: If provider doesn't support vision or input validation fails.
        """
        # 1. Select provider from settings
        selected_provider = self._resolve_provider()

        # 2. Resolve final model
        final_model = self._resolve_model(
            model_hint,
            selected_provider,
            missing_message="Model hint must be provided for vision request.",
        )

        # 3. Validate provider supports vision
        if selected_provider not in (APIProvider.OPENAI, APIProvider.GOOGLE):
            raise ValueError(f"Provider '{selected_provider.value}' does not support vision requests.")

        # 3.5. Validate input: require at least one image part for vision request
        has_image = False
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        has_image = True
                        break
            if has_image:
                break
        if not has_image:
            raise ValueError("Vision request requires an image part")

        logger.debug(f"Vision request: provider={selected_provider.value}, model={final_model}")

        # 4. Build LLM params
        api_params = self._build_llm_params(final_model, messages)

        # 5. Route to adapter (both providers now use the same path)
        response = self.make_request_sync(
            selected_provider,
            **api_params
        )
        return response, final_model

    def extract_text_from_response(self, response: Any) -> str:
        """
        Safely extracts text content from API response objects.

        Handles both object-based responses (OpenAI-like) and dict-based responses.
        Logs response structure on first extraction failure for debugging.

        Args:
            response: API response object (OpenAI-like structure or dict)

        Returns:
            Extracted text content, or empty string if extraction fails
        """
        try:
            # Try dict-based structure first (Google Gemini normalized)
            if isinstance(response, dict) and 'choices' in response and response['choices']:
                choice = response['choices'][0]
                if isinstance(choice, dict) and 'message' in choice:
                    message = choice['message']
                    if isinstance(message, dict) and 'content' in message:
                        return message['content']
        except (KeyError, IndexError, TypeError):
            pass

        try:
            # Try OpenAI-like object structure
            if not isinstance(response, dict) and hasattr(response, 'choices'):
                choices = getattr(response, 'choices', [])
                if choices:
                    choice = choices[0]
                    if hasattr(choice, 'message'):
                        message = choice.message
                        if hasattr(message, 'content'):
                            return getattr(message, 'content', '')
        except (AttributeError, IndexError, TypeError):
            pass

        # Log response structure for debugging on first failure
        if not hasattr(self, '_logged_response_structure'):
            logger.warning(f"Failed to extract text from response. Response type: {type(response)}")
            try:
                logger.debug(f"Response structure: {response}")
                if hasattr(response, '__dict__'):
                    logger.debug(f"Response attributes: {dir(response)}")
            except Exception as e:
                logger.debug(f"Could not log response structure: {e}")
            self._logged_response_structure = True

        return ""

    @requires_initialization
    def get_available_models_sync(self, provider: APIProvider, temp_api_key: Optional[str] = None) -> tuple[List[str], str]:
        """
        Get list of available models from API provider.

        Args:
            provider: The API provider to query.
            temp_api_key: If provided, use this key for a one-off request
                          instead of the configured client.

        Returns:
            Tuple of (models_list, source).
        """
        return self._model_manager.get_available_models(provider, temp_api_key)

    def shutdown(self) -> None:
        """Shutdown API manager and cleanup resources."""
        with self._lock:
            self._providers.clear()
            self._cache.clear()
            self._is_initialized = False
            logger.info("API manager shutdown")


__all__ = [
    "APIManager",
]
