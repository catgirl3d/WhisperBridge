"""
API Manager for WhisperBridge.

This module provides centralized API management with authentication,
error handling, retry logic, and usage monitoring.
"""

import json
import threading
import time
import os
import sys
import platform
import importlib
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..services.config_service import ConfigService, config_service
from ..providers.google_chat_adapter import GoogleChatClientAdapter
from ..providers.deepl_adapter import DeepLClientAdapter
from ..providers.openai_adapter import OpenAIChatClientAdapter, DEFAULT_GPT_MODELS
from .config import (
    ensure_config_dir,
    validate_api_key_format,
    get_deepl_identifier,
    get_google_model_excludes,
    get_openai_model_excludes,
)
from .model_limits import calculate_dynamic_completion_tokens, DEFAULT_MIN_OUTPUT_TOKENS


def _model_supports_temperature(model: str) -> bool:
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


def _adjust_temperature_for_model(model: str, temperature: float) -> float:
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
    if not _model_supports_temperature(model):
        if temperature != 1.0:
            logger.info(
                f"Model '{model}' does not support custom temperature. "
                f"Overriding {temperature} -> 1.0"
            )
        return 1.0
    return temperature


def requires_initialization(func):
    """Decorator to ensure API manager is initialized before method execution."""
    @wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        if not self.is_initialized():
            raise RuntimeError("API manager not initialized")
        return func(self, *args, **kwargs)

    return sync_wrapper


class APIProvider(Enum):
    """Supported API providers."""

    OPENAI = "openai"
    GOOGLE = "google"
    DEEPL = "deepl"


class APIErrorType(Enum):
    """Types of API errors."""

    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXCEEDED = "quota_exceeded"
    NETWORK = "network"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


class ModelSource(Enum):
    """Sources for model listings."""

    CACHE = "cache"
    API = "api"
    API_TEMP_KEY = "api_temp_key"
    UNCONFIGURED = "unconfigured"
    FALLBACK = "fallback"
    ERROR = "error"



@dataclass
class APIUsage:
    """API usage statistics."""

    requests_count: int = 0
    tokens_used: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_request_time: Optional[datetime] = None
    rate_limit_hits: int = 0



@dataclass
class APIError:
    """API error information."""

    error_type: APIErrorType
    message: str
    status_code: Optional[int] = None
    retry_after: Optional[int] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class RetryableAPIError(Exception):
    """Custom exception to signal a retryable API error."""

    pass


class APIManager:
    """Centralized API manager for handling authentication and requests."""

    def __init__(self, config_service: ConfigService):
        """
        Initialize the APIManager.

        Args:
            config_service: The application's configuration service.
        """
        self.config_service = config_service
        self._clients: Dict[APIProvider, Any] = {}
        self._usage: Dict[APIProvider, APIUsage] = {}
        self._lock = threading.RLock()
        self._is_initialized = False
        self._model_cache: Dict[APIProvider, tuple] = {}  # (models_list, timestamp)
        self._model_cache_ttl = 1209600  # 2 weeks cache
        self._diag_logged = False  # log network/SSL diagnostics once

    def _get_model_cache_path(self) -> Path:
        """Return path to persistent model cache file."""
        config_dir = ensure_config_dir()
        return config_dir / "models_cache.json"

    def _load_model_cache_from_disk(self):
        """Load persistent model cache into memory if present."""
        path = self._get_model_cache_path()
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        with self._lock:
            # raw expected as {provider_value: {"models": [...], "timestamp": ts}}
            for prov_str, entry in raw.items():
                try:
                    prov = APIProvider(prov_str)
                except Exception:
                    continue
                models = entry.get("models", [])
                ts = entry.get("timestamp", 0)
                self._model_cache[prov] = (models, ts)
            logger.info("Loaded model cache from disk")

    def _save_model_cache_to_disk(self):
        """Persist in-memory model cache to disk."""
        path = self._get_model_cache_path()
        data = {}
        with self._lock:
            for prov, (models, ts) in self._model_cache.items():
                data[prov.value] = {"models": models, "timestamp": ts}
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Saved model cache to disk")

    def _cleanup_old_cache_files(self):
        """Remove cache files older than TTL."""
        try:
            path = self._get_model_cache_path()
            if path.exists():
                file_age = time.time() - path.stat().st_mtime
                if file_age > self._model_cache_ttl:
                    path.unlink()
                    logger.debug("Removed old model cache file")
        except Exception as e:
            logger.debug(f"Failed to cleanup old cache files: {e}")

    def _handle_cache_operation(self, operation: str, operation_func: Callable):
        """Universal cache operation handler with error logging."""
        try:
            return operation_func()
        except Exception as e:
            logger.warning(f"Failed to {operation} model cache: {e}")
            return None

    def _cache_models_and_persist(self, provider: APIProvider, models: List[str]) -> None:
        """Cache models and persist to disk in one operation."""
        with self._lock:
            self._model_cache[provider] = (models, time.time())
        self._handle_cache_operation("persist", self._save_model_cache_to_disk)

    def _initialize_cache_safely(self):
        """Safely initialize model cache with error handling."""

        def load_cache():
            self._load_model_cache_from_disk()
            self._cleanup_old_cache_files()

        self._handle_cache_operation("load cache during initialization", load_cache)

    def _validate_model_list(self, models: List[str]) -> bool:
        """Validate that model list is not empty and contains valid strings."""
        if not models:
            return False
        return all(isinstance(model, str) and model.strip() for model in models)

    def _get_default_models(self) -> List[str]:
        """Get default model list with optional configuration override."""
        try:
            # Check for custom models in configuration
            custom_models = self.config_service.get_setting("default_models", use_cache=False)
            if custom_models and isinstance(custom_models, list) and self._validate_model_list(custom_models):
                logger.debug(f"Using custom default models from config: {custom_models}")
                return custom_models.copy()
        except Exception as e:
            logger.warning(f"Failed to get custom default models from config: {e}")

        # Fallback to built-in default models
        logger.debug(f"Using built-in default models: {DEFAULT_GPT_MODELS}")
        return DEFAULT_GPT_MODELS.copy()

    def _initialize_providers(self):
        """Initialize all available API providers.

        This method attempts to initialize OpenAI, Google and DeepL providers
        to ensure seamless switching between them in the UI without needing
        to restart or re-save settings.
        """
        logger.debug("Initializing all available API providers.")

        # Always try to initialize all providers
        self._init_openai_provider()
        self._init_google_provider()
        self._init_deepl_provider()

        selected_provider = (self.config_service.get_setting("api_provider") or "").strip().lower()
        if not selected_provider:
            logger.warning("No default API provider is selected in settings.")

    def _initialize_provider(
        self,
        provider: APIProvider,
        config_key_name: str,
        key_prefix: str,
        client_factory: Callable[[str, Optional[int]], Any],
        provider_name: str,
    ):
        """
        Generic method to initialize an API provider.

        Args:
            provider: The APIProvider enum member.
            config_key_name: The key for the API key in config_service.
            key_prefix: The expected prefix for the API key for validation.
            client_factory: A function that takes an api_key and timeout and returns a client.
            provider_name: The user-friendly name of the provider for logging.
        """
        api_key = self.config_service.get_setting(config_key_name)
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
            timeout = self.config_service.get_setting("api_timeout")
            client = client_factory(api_key, timeout)
            self._clients[provider] = client
            self._usage[provider] = APIUsage()
            logger.info(f"{provider_name} client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize {provider_name} provider: {e}")

    def _init_openai_provider(self):
        """Initialize OpenAI provider with graceful degradation."""
        self._initialize_provider(
            provider=APIProvider.OPENAI,
            config_key_name="openai_api_key",
            key_prefix="sk-",
            client_factory=lambda key, timeout: OpenAIChatClientAdapter(api_key=key, timeout=timeout),
            provider_name="OpenAI",
        )

    def _init_google_provider(self):
        """Initialize Google Generative AI (Gemini) provider with minimal adapter."""
        self._initialize_provider(
            provider=APIProvider.GOOGLE,
            config_key_name="google_api_key",
            key_prefix="AIza",
            client_factory=lambda key, timeout: GoogleChatClientAdapter(api_key=key, timeout=timeout),
            provider_name="Google Generative AI",
        )

    def _init_deepl_provider(self):
        """Initialize DeepL translation provider (non-LLM)."""
        self._initialize_provider(
            provider=APIProvider.DEEPL,
            config_key_name="deepl_api_key",
            key_prefix="",  # DeepL keys don't have a stable prefix
            client_factory=lambda key, timeout: DeepLClientAdapter(
                api_key=key,
                timeout=timeout,
                plan=(self.config_service.get_setting("deepl_plan") or "free"),
            ),
            provider_name="DeepL",
        )

    def _finalize_initialization(self):
        """Finalize initialization with consistent status setting and cache loading."""
        # Allow initialization even without API clients
        # The app can still run OCR and other features
        self._is_initialized = True

        # Load any persistent model cache from disk so first-run UI can use it
        self._initialize_cache_safely()

        if self._clients:
            logger.info("API manager initialized successfully with clients")
        else:
            logger.info("API manager initialized (no API clients - translation features disabled)")

    def _get_fallback_models(self, provider: APIProvider) -> tuple[List[str], str]:
        """Get fallback models with caching."""
        if provider == APIProvider.GOOGLE:
            fallback_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        elif provider == APIProvider.DEEPL:
            fallback_models = [get_deepl_identifier()]
        else:
            fallback_models = self._get_default_models()
        self._cache_models_and_persist(provider, fallback_models)
        return fallback_models, ModelSource.FALLBACK.value

    def initialize(self) -> bool:
        """Initialize API manager with configured providers."""
        with self._lock:
            success = False
            try:
                self._initialize_providers()
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

        Clears existing clients and usage statistics, then re-runs the standard
        initialization workflow so the manager picks up refreshed credentials or
        provider settings. Model cache is cleared to ensure fresh API calls with
        new credentials.
        """
        logger.info("Reinitializing API manager with updated settings")
        with self._lock:
            self._clients.clear()
            self._usage.clear()
            self._model_cache.clear()  # Clear model cache to force fresh API calls
            self._is_initialized = False

        return self.initialize()

    def is_initialized(self) -> bool:
        """Check if API manager is initialized."""
        return self._is_initialized

    def has_clients(self) -> bool:
        """Check if any API clients are configured."""
        with self._lock:
            return bool(self._clients)

    def _classify_error(self, error: Exception) -> APIError:
        """Classify exception into API error type."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # Authentication errors
        if any(keyword in error_str for keyword in ["unauthorized", "invalid api key", "authentication"]):
            return APIError(APIErrorType.AUTHENTICATION, str(error))

        # Rate limit errors
        if any(keyword in error_str for keyword in ["rate limit", "too many requests"]):
            retry_after = None
            if hasattr(error, "retry_after"):
                retry_after = getattr(error, "retry_after", None)
            return APIError(APIErrorType.RATE_LIMIT, str(error), retry_after=retry_after)

        # Quota exceeded
        if any(keyword in error_str for keyword in ["quota", "billing"]):
            return APIError(APIErrorType.QUOTA_EXCEEDED, str(error))

        # Network/timeout errors
        if any(keyword in error_type for keyword in ["timeout", "connection"]):
            return APIError(APIErrorType.TIMEOUT, str(error))
        if any(keyword in error_str for keyword in ["network", "connection", "dns"]):
            return APIError(APIErrorType.NETWORK, str(error))

        # Invalid request
        if any(keyword in error_str for keyword in ["invalid", "bad request", "malformed"]):
            return APIError(APIErrorType.INVALID_REQUEST, str(error))

        # Server errors
        if hasattr(error, "status_code"):
            status_code = getattr(error, "status_code", None)
            if status_code and status_code >= 500:
                return APIError(APIErrorType.SERVER_ERROR, str(error), status_code)

        # Unknown error
        return APIError(APIErrorType.UNKNOWN, str(error))

    def _log_network_diagnostics(self):
        """Log one-shot diagnostics to investigate crashes in frozen builds."""
        try:
            info: Dict[str, Any] = {
                "frozen": getattr(sys, "frozen", False),
                "meipass": getattr(sys, "_MEIPASS", None),
                "python": sys.version,
                "platform": platform.platform(),
                "executable": getattr(sys, "executable", None),
                "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE"),
                "REQUESTS_CA_BUNDLE": os.environ.get("REQUESTS_CA_BUNDLE"),
            }
            # certifi
            try:
                import certifi  # type: ignore
                info["certifi.where"] = certifi.where()
                info["certifi.file"] = getattr(certifi, "__file__", None)
            except Exception as e:
                info["certifi.error"] = str(e)

            def _mod_info(name: str) -> Dict[str, Any]:
                try:
                    m = importlib.import_module(name)
                    return {
                        "file": getattr(m, "__file__", None),
                        "version": getattr(m, "__version__", None),
                    }
                except Exception as ex:
                    return {"error": str(ex)}

            # Critical runtime modules
            info["openai"] = _mod_info("openai")
            info["httpx"] = _mod_info("httpx")
            info["httpcore"] = _mod_info("httpcore")
            info["h11"] = _mod_info("h11")
            info["pydantic_core"] = _mod_info("pydantic_core")

            logger.debug(f"Network diagnostics (once): {info}")
        except Exception as e:
            logger.debug(f"Failed to log network diagnostics: {e}")

    @requires_initialization
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(RetryableAPIError),
    )
    def make_request_sync(self, provider: APIProvider, **kwargs) -> Any:
        """Make API request with retry logic."""
        client = self._clients.get(provider)
        if not client:
            raise ValueError(f"Provider {provider.value} not configured. Please set up your API key in settings.")

        usage = self._usage.get(provider, APIUsage())

        try:
            logger.debug(f"Making API request to provider '{provider.value}' with args: {kwargs}")
            if not self._diag_logged:
                self._log_network_diagnostics()
                self._diag_logged = True
            start_time = time.time()
            response = client.chat.completions.create(**kwargs)
            request_time = time.time() - start_time
            logger.debug(f"Raw API response: {response}")

            with self._lock:
                usage.requests_count += 1
                usage.successful_requests += 1
                usage.last_request_time = datetime.now()
                if hasattr(response, "usage") and response.usage:
                    usage.tokens_used += response.usage.total_tokens

            logger.debug(f"API request completed in {request_time:.2f}s")
            return response

        except Exception as e:
            error_str = str(e).lower()
            
            # Handle unsupported temperature error by retrying without temperature parameter
            if "unsupported_value" in error_str and "temperature" in error_str:
                logger.warning(
                    f"Temperature parameter not supported by this model. "
                    f"Retrying without temperature parameter (API default). Original error: {e}"
                )
                # Remove temperature from kwargs and retry once
                retry_kwargs = kwargs.copy()
                retry_kwargs.pop("temperature", None)
                
                try:
                    response = client.chat.completions.create(**retry_kwargs)
                    request_time = time.time() - start_time
                    logger.debug(f"API request completed in {request_time:.2f}s (retried without temperature)")

                    with self._lock:
                        usage.requests_count += 1
                        usage.successful_requests += 1
                        usage.last_request_time = datetime.now()
                        if hasattr(response, "usage") and response.usage:
                            usage.tokens_used += response.usage.total_tokens

                    return response
                except Exception as retry_e:
                    # If retry also fails, fall through to normal error handling
                    logger.debug(f"Retry without temperature also failed: {retry_e}")
                    e = retry_e
            
            api_error = self._classify_error(e)

            with self._lock:
                usage.requests_count += 1
                usage.failed_requests += 1
                if api_error.error_type == APIErrorType.RATE_LIMIT:
                    usage.rate_limit_hits += 1

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
        self, messages: List[Dict[str, Any]], model_hint: Optional[str] = None, temperature: Optional[float] = None, **api_kwargs
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
            temperature: Optional temperature override.
            api_kwargs: Additional provider-specific kwargs (e.g., target_lang/source_lang for DeepL).

        Returns:
            A tuple containing the API response and the model name used.
        """
        # 1. Select the configured provider
        provider_name = (self.config_service.get_setting("api_provider") or "openai").strip().lower()
        try:
            selected_provider = APIProvider(provider_name)
        except ValueError:
            raise RuntimeError(f"Invalid API provider '{provider_name}' configured in settings.")

        if selected_provider not in self._clients:
            raise RuntimeError(
                f"The configured API provider '{provider_name}' is not available. "
                "Please check your API key in the settings."
            )

        # 2. Use the provided model hint directly (with DeepL special-case)
        final_model = (model_hint or "").strip()
        if selected_provider == APIProvider.DEEPL:
            # DeepL doesn't use real models; use a fixed identifier
            if not final_model:
                final_model = get_deepl_identifier()
            api_params = {
                "model": final_model,
                "messages": messages,
            }
            # Pass through DeepL specifics if provided (e.g., target_lang/source_lang)
            for k, v in (api_kwargs or {}).items():
                if v is not None:
                    api_params[k] = v
            logger.debug(f"Final API parameters for {selected_provider.value}: {api_params}")
            response = self.make_request_sync(selected_provider, **api_params)
            return response, final_model

        if not final_model:
            raise ValueError("Model name must be provided for the translation request.")

        # 3. Prepare API call parameters for LLM providers
        # Calculate max output tokens with dynamic model limits
        max_completion_tokens = calculate_dynamic_completion_tokens(
            model=final_model,
            min_output_tokens=DEFAULT_MIN_OUTPUT_TOKENS,
            output_safety_margin=0.1
        )
        
        # Use provided temperature or fall back to translation temperature setting
        if temperature is None:
            try:
                val = self.config_service.get_setting("llm_temperature_translation")
                translation_temp = round(float(val if val is not None else 1.0), 2)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse translation temperature from config, using default 1.0. Error: {e}")
                translation_temp = 1.0
        else:
            try:
                translation_temp = round(float(temperature), 2)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse provided temperature '{temperature}', using default 1.0. Error: {e}")
                translation_temp = 1.0
        
        # Adjust temperature based on model capabilities
        translation_temp = _adjust_temperature_for_model(final_model, translation_temp)
        
        api_params = {
            "model": final_model,
            "messages": messages,
            "temperature": translation_temp,
            "max_completion_tokens": max_completion_tokens,
        }
        
        logger.debug(f"Translation temperature: {translation_temp}, max_completion_tokens={max_completion_tokens}")

        logger.debug(f"Final API parameters for {selected_provider.value}: {api_params}")

        # 4. Make the API call
        response = self.make_request_sync(selected_provider, **api_params)

        return response, final_model

    @requires_initialization
    def make_vision_request(self, messages: list[dict], model_hint: str) -> tuple[object, str]:
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
        provider_name = (self.config_service.get_setting("api_provider") or "openai").strip().lower()
        try:
            selected_provider = APIProvider(provider_name)
        except ValueError:
            raise RuntimeError(f"Invalid API provider '{provider_name}' configured in settings.")

        if selected_provider not in self._clients:
            raise RuntimeError(
                f"The configured API provider '{provider_name}' is not available. "
                "Please check your API key in the settings."
            )

        # 2. Resolve final model
        final_model = (model_hint or "").strip()
        if not final_model:
            raise ValueError("Model hint must be provided for vision request.")

        if selected_provider == APIProvider.OPENAI:
            # Use model_hint directly (typically settings.openai_vision_model)
            pass
        elif selected_provider == APIProvider.GOOGLE:
            # Use model_hint directly (typically settings.google_vision_model)
            pass
        else:
            raise ValueError(f"Provider '{selected_provider.value}' does not support vision requests.")

        logger.debug(f"Vision request: provider={selected_provider.value}, model={final_model}")

        # 3. Route to provider-specific implementation
        if selected_provider == APIProvider.OPENAI:
            # Get temperature from config for vision
            try:
                val = self.config_service.get_setting("llm_temperature_vision")
                vision_temp = round(float(val if val is not None else 0.0), 2)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse vision temperature from config (OpenAI), using default 0.0. Error: {e}")
                vision_temp = 0.0
            
            # Adjust temperature based on model capabilities
            vision_temp = _adjust_temperature_for_model(final_model, vision_temp)
            
            # Delegate to adapter's vision method
            response = self.make_request_sync(APIProvider.OPENAI, model=final_model, messages=messages, temperature=vision_temp, is_vision=True)
            return response, final_model
        elif selected_provider == APIProvider.GOOGLE:
            return self._make_google_vision_request(messages, final_model)
        else:
            # Should not reach here due to check above, but defensive
            raise ValueError(f"Unsupported vision provider: {selected_provider.value}")

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

    def _make_google_vision_request(self, messages: list[dict], model: str) -> tuple[object, str]:
        """Handle Google Gemini vision request with direct SDK usage and retry."""
        # Validate input: require at least one image part for Gemini
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
            raise ValueError("Gemini vision request requires an image part")

        # Separate system instruction and user content
        system_parts = []
        user_text_parts = []
        image_data = None
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            
            if role == "system":
                system_parts.append(str(content or ""))
            elif role == "user":
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                user_text_parts.append(part.get("text", ""))
                            elif part.get("type") == "image_url" and not image_data:
                                # Decode first image
                                image_url = part.get("image_url", {}).get("url", "")
                                if image_url.startswith("data:image/jpeg;base64,"):
                                    try:
                                        image_data = base64.b64decode(image_url[23:])  # Strip prefix
                                    except Exception as e:
                                        raise ValueError(f"Failed to decode image data URL: {e}")
                                else:
                                    raise ValueError("Unsupported image URL format; expected data:image/jpeg;base64,...")
                elif isinstance(content, str):
                    user_text_parts.append(content)

        system_instruction = " ".join(system_parts).strip() or None
        prompt = " ".join(user_text_parts).strip() or "Describe this image"
        
        if not image_data:
            raise ValueError("No valid image data found in messages")

        # Lazy import and call Gemini with new SDK
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai package not available")

        api_key = self.config_service.get_setting("google_api_key")
        if not api_key:
            raise RuntimeError("Google API key not configured")

        timeout = self.config_service.get_setting("api_timeout")
        client = genai.Client(api_key=api_key, http_options={"timeout": (timeout or 30) * 1000})
        
        # Configure generation parameters with dynamic token allocation
        max_output_tokens = calculate_dynamic_completion_tokens(
            model=model,
            min_output_tokens=DEFAULT_MIN_OUTPUT_TOKENS,
            output_safety_margin=0.1
        )
        
        # Get temperature from config for vision
        try:
            val = self.config_service.get_setting("llm_temperature_vision")
            vision_temp = round(float(val if val is not None else 0.0), 2)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse vision temperature from config (Google), using default 0.0. Error: {e}")
            vision_temp = 0.0
        
        # Adjust temperature based on model capabilities
        vision_temp = _adjust_temperature_for_model(model, vision_temp)
        
        logger.debug(f"Google vision temperature: {vision_temp}, max_output_tokens={max_output_tokens}")
        
        config = types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=vision_temp,
            system_instruction=system_instruction,
        )

        # Add ThinkingConfig for Gemini 3 vision models
        if model.startswith("gemini-3"):
            from google.genai.types import ThinkingLevel
            config.thinking_config = types.ThinkingConfig(thinking_level=ThinkingLevel.LOW)

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=60),
            retry=retry_if_exception_type(RetryableAPIError),
        )
        def do_gemini_call():
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=image_data, mime_type="image/jpeg")
                    ],
                    config=config
                )
                return response
            except Exception as e:
                api_error = self._classify_error(e)
                if api_error.error_type in [
                    APIErrorType.RATE_LIMIT,
                    APIErrorType.NETWORK,
                    APIErrorType.TIMEOUT,
                    APIErrorType.SERVER_ERROR,
                ]:
                    raise RetryableAPIError(f"Retryable Gemini error: {api_error.message}") from e
                else:
                    raise e

        gemini_response = do_gemini_call()

        # Extract text from new SDK response (pydantic object)
        logger.debug(f"Gemini response object: {gemini_response}")
        
        try:
            extracted_text = gemini_response.text or ""
        except (ValueError, AttributeError):
            # Response may be blocked by safety filters or have no valid parts
            logger.warning("Failed to extract text from Gemini response (blocked or empty)")
            extracted_text = ""

        # Calculate total tokens correctly (usage_metadata is an object, not a dict)
        usage_metadata = getattr(gemini_response, "usage_metadata", None)
        total_tokens = 0
        if usage_metadata is not None:
            total_tokens = getattr(usage_metadata, "total_token_count", None) or (
                getattr(usage_metadata, "input_token_count", 0)
                + getattr(usage_metadata, "output_token_count", 0)
            )

        # Create standardized dict response for consistency
        normalized_response = {
            "choices": [
                {
                    "message": {
                        "content": extracted_text
                    }
                }
            ],
            "model": model,
            "usage": {
                "total_tokens": total_tokens
            }
        }

        return normalized_response, model


    @requires_initialization
    def get_usage_stats(self, provider: Optional[APIProvider] = None) -> Dict[str, Any]:
        """Get API usage statistics."""
        with self._lock:
            if provider:
                usage = self._usage.get(provider, APIUsage())
                return {
                    "provider": provider.value,
                    "requests_count": usage.requests_count,
                    "tokens_used": usage.tokens_used,
                    "successful_requests": usage.successful_requests,
                    "failed_requests": usage.failed_requests,
                    "success_rate": (usage.successful_requests / usage.requests_count * 100) if usage.requests_count > 0 else 0,
                    "last_request_time": usage.last_request_time.isoformat() if usage.last_request_time else None,
                    "rate_limit_hits": usage.rate_limit_hits,
                }
            else:
                # Return stats for all providers
                stats = {}
                for prov, usage in self._usage.items():
                    stats[prov.value] = self.get_usage_stats(prov)
                return stats

    @requires_initialization
    def is_rate_limited(self, provider: APIProvider) -> bool:
        """Check if provider is currently rate limited."""
        usage = self._usage.get(provider, APIUsage())

        # Simple rate limiting check based on recent failures
        if usage.rate_limit_hits > 5:
            # Check if we should reset the counter (after some time)
            if usage.last_request_time:
                time_since_last = datetime.now() - usage.last_request_time
                if time_since_last > timedelta(minutes=5):
                    with self._lock:
                        usage.rate_limit_hits = 0
                    return False
            return True

        return False

    @requires_initialization
    def get_available_models_sync(self, provider: APIProvider, temp_api_key: Optional[str] = None) -> tuple[List[str], str]:
        """
        Get list of available models from API provider.

        Args:
            provider: The API provider to query.
            temp_api_key: If provided, use this key for a one-off request
                          instead of the configured client.
        """
        # 0. If provider is not configured and no temp key is provided, report UNCONFIGURED (ignore cache)
        if not temp_api_key:
            with self._lock:
                is_configured = provider in self._clients
            if not is_configured:
                logger.debug(f"Provider {provider.value} not configured - ignoring cache and reporting UNCONFIGURED")
                return [], ModelSource.UNCONFIGURED.value

        # 1. Check cache first, but only if not using a temporary key
        if not temp_api_key:
            with self._lock:
                if provider in self._model_cache:
                    models, timestamp = self._model_cache[provider]
                    # Only use cache if it's not expired and NOT empty (unless it's DeepL which has a virtual model)
                    if time.time() - timestamp < self._model_cache_ttl:
                        if models or provider == APIProvider.DEEPL:
                            logger.debug(f"Using cached models for {provider.value}")
                            # Apply global filters to cached data to ensure any newly added exclusions take effect
                            filtered_models = self._apply_global_filters(provider, models)
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
            client = self._clients.get(provider)

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
                models = self._apply_global_filters(provider, gemini_models)
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
                    self._cache_models_and_persist(provider, models)
            return models, source.value

        except Exception as e:
            logger.error(f"Failed to fetch models from {provider.value}: {e}")
            # Clear cache entry for this provider to prevent caching empty/error results
            with self._lock:
                self._model_cache.pop(provider, None)
            return [], ModelSource.ERROR.value

    def _apply_global_filters(self, provider: APIProvider, model_ids: List[str]) -> List[str]:
        """Apply global exclusion filters to a list of model IDs."""
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

    def shutdown(self):
        """Shutdown API manager and cleanup resources."""
        with self._lock:
            self._clients.clear()
            self._usage.clear()
            self._model_cache.clear()
            self._is_initialized = False
            logger.info("API manager shutdown")


# Global API manager instance
_api_manager: Optional[APIManager] = None
_manager_lock = threading.RLock()


def get_api_manager() -> APIManager:
    """
    Get the global API manager instance.

    This function ensures that a single instance of the APIManager is used throughout
    the application. It uses a lock to be thread-safe.
    """
    global _api_manager
    with _manager_lock:
        if _api_manager is None:
            # Pass the global config_service instance to the APIManager
            _api_manager = APIManager(config_service)
        return _api_manager


def init_api_manager() -> APIManager:
    """
    Initialize and return the API manager instance.

    This function retrieves the global APIManager instance and initializes it if it
    hasn't been already.
    """
    manager = get_api_manager()
    if not manager.is_initialized():
        if not manager.initialize():
            raise RuntimeError("Failed to initialize API manager")
    return manager
