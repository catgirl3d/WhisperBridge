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

import openai
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
from .config import (
    ensure_config_dir,
    validate_api_key_format,
    get_deepl_identifier,
)


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
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class RetryableAPIError(Exception):
    """Custom exception to signal a retryable API error."""

    pass


class APIManager:
    """Centralized API manager for handling authentication and requests."""

    # Default GPT models list to avoid duplication
    DEFAULT_GPT_MODELS = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o-mini"]

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
            custom_models = self.config_service.get_setting("default_models", None)
            if custom_models and isinstance(custom_models, list) and self._validate_model_list(custom_models):
                logger.debug(f"Using custom default models from config: {custom_models}")
                return custom_models.copy()
        except Exception as e:
            logger.warning(f"Failed to get custom default models from config: {e}")

        # Fallback to built-in default models
        logger.debug(f"Using built-in default models: {self.DEFAULT_GPT_MODELS}")
        return self.DEFAULT_GPT_MODELS.copy()

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
            client_factory=lambda key, timeout: openai.OpenAI(api_key=key, timeout=timeout),
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
            try:
                self._initialize_providers()
                self._finalize_initialization()
                return True
            except Exception as e:
                logger.error(f"Failed to initialize API manager: {e}")
                # Still allow initialization even if there are errors
                self._is_initialized = False  # Set to False as initialization failed
                logger.warning("API manager failed to initialize; limited offline cache may be available")
                # Try loading cache even on errors to provide offline model list
                self._initialize_cache_safely()
                return False  # Return False to indicate failure

    def reinitialize(self) -> bool:
        """
        Reinitialize API manager using the latest configuration values.

        Clears existing clients and usage statistics, then re-runs the standard
        initialization workflow so the manager picks up refreshed credentials or
        provider settings. Model cache is intentionally left intact to reuse any
        previously fetched lists when still valid.
        """
        logger.info("Reinitializing API manager with updated settings")
        with self._lock:
            self._clients.clear()
            self._usage.clear()
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
                retry_after = error.retry_after
            return APIError(APIErrorType.RATE_LIMIT, str(error), retry_after=retry_after)

        # Quota exceeded
        if any(keyword in error_str for keyword in ["quota", "exceeded", "insufficient"]):
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
        if hasattr(error, "status_code") and error.status_code >= 500:
            return APIError(APIErrorType.SERVER_ERROR, str(error), error.status_code)

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
                APIErrorType.QUOTA_EXCEEDED,
            ]:
                # Wrap in custom exception to trigger tenacity retry
                raise RetryableAPIError(f"Retryable error occurred: {api_error.message}") from e

            # For non-retryable errors, re-raise the original exception
            raise e

    @requires_initialization
    def make_translation_request(
        self, messages: List[Dict[str, str]], model_hint: Optional[str] = None, **api_kwargs
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
        api_params = {
            "model": final_model,
            "messages": messages,
            "temperature": 1,
            "max_completion_tokens": 2048,
        }

        if selected_provider == APIProvider.OPENAI:
            if final_model.startswith(("gpt-5", "chatgpt")):
                api_params["extra_body"] = {"reasoning_effort": "minimal", "verbosity": "low"}
                logger.debug("Using OpenAI GPT-5 optimizations: reasoning_effort=minimal, verbosity=low")
            elif final_model.startswith("gpt-"):
                api_params["extra_body"] = {"reasoning_effort": "minimal"}
                logger.debug("Using OpenAI GPT optimizations: reasoning_effort=minimal")

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
            return self._make_openai_vision_request(messages, final_model)
        elif selected_provider == APIProvider.GOOGLE:
            return self._make_google_vision_request(messages, final_model)
        else:
            # Should not reach here due to check above, but defensive
            raise ValueError(f"Unsupported vision provider: {selected_provider.value}")

    def _make_openai_vision_request(self, messages: list[dict], model: str) -> tuple[object, str]:
        """Handle OpenAI vision request via make_request_sync."""
        response = self.make_request_sync(
            APIProvider.OPENAI,
            model=model,
            messages=messages,
            temperature=0,
            max_completion_tokens=2048,
        )
        return response, model

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

        # Extract text and image from messages (concatenate all text, use first image)
        text_parts = []
        image_data = None
        for msg in messages:
            if msg.get("role") == "system":
                text_parts.append(msg.get("content", ""))
            elif msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
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

        prompt = " ".join(text_parts).strip()
        if not image_data:
            raise ValueError("No valid image data found in messages")

        # Lazy import and call Gemini
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError("google-generativeai package not available")

        api_key = self.config_service.get_setting("google_api_key")
        if not api_key:
            raise RuntimeError("Google API key not configured")

        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel(model)
        parts = [prompt, {"mime_type": "image/jpeg", "data": image_data}]

        generation_config = {"max_output_tokens": 2048, "temperature": 0}

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=60),
            retry=retry_if_exception_type(RetryableAPIError),
        )
        def do_gemini_call():
            try:
                response = gemini_model.generate_content(parts, generation_config=generation_config)
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

        # Normalize to OpenAI-like structure
        logger.debug(f"Gemini response object: {gemini_response}")
        logger.debug(f"Gemini response attributes: {dir(gemini_response)}")

        try:
            extracted_text = gemini_response.text or ""
            logger.debug(f"Successfully extracted text using .text: '{extracted_text}'")
        except Exception as e:
            logger.warning(f"Failed to extract text using .text: {e}")
            # Fallback if response.text fails
            extracted_text = ""
            if hasattr(gemini_response, 'candidates') and gemini_response.candidates:
                logger.debug(f"Using candidates fallback, found {len(gemini_response.candidates)} candidates")
                for candidate in gemini_response.candidates:
                    logger.debug(f"Processing candidate: {candidate}")
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        logger.debug(f"Content has {len(candidate.content.parts)} parts")
                        for part in candidate.content.parts:
                            logger.debug(f"Processing part: {part}")
                            if hasattr(part, 'text'):
                                extracted_text += part.text or ""
                                logger.debug(f"Extracted text from part: '{part.text}'")
                            break
                        break
            else:
                logger.warning("No candidates found in Gemini response")

        # Calculate total tokens correctly (usage_metadata is an object, not a dict)
        usage_metadata = getattr(gemini_response, "usage_metadata", None)
        total_tokens = 0
        if usage_metadata is not None:
            total_tokens = getattr(usage_metadata, "total_token_count", None) or (
                getattr(usage_metadata, "input_token_count", 0)
                + getattr(usage_metadata, "output_token_count", 0)
            )

        # Create OpenAI-like response object for consistency
        class _Message:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, message):
                self.message = message

        class _Usage:
            def __init__(self, total_tokens):
                self.total_tokens = total_tokens

        class _Response:
            def __init__(self, choices, model, usage):
                self.choices = choices
                self.model = model
                self.usage = usage

        message = _Message(extracted_text)
        choice = _Choice(message)
        usage = _Usage(total_tokens)

        normalized_response = _Response([choice], model, usage)

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
                    if time.time() - timestamp < self._model_cache_ttl:
                        logger.debug(f"Using cached models for {provider.value}")
                        return models, ModelSource.CACHE.value

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
            client = self._clients.get(provider)

        # 3. If no client could be determined, exit
        if not client:
            logger.debug(f"Provider {provider.value} not configured and no valid temp key provided.")
            return [], ModelSource.UNCONFIGURED.value

        # 4. Now, fetch models using the determined client
        try:
            if provider == APIProvider.OPENAI:
                models_response = client.models.list()
                all_models = [model.id for model in models_response.data]
                logger.debug(f"All available models from API: {all_models}")
                chat_models = [
                    model.id for model in models_response.data
                    if (model.id.lower().startswith("gpt-") or model.id.lower().startswith("chatgpt-"))
                    and not any(
                        exclude in model.id.lower()
                        for exclude in ["audio", "realtime", "image", "dall-e", "tts", "whisper", "embedding", "moderation", "codex"]
                    )
                    and not model.id.lower().startswith("gpt-3")
                ]
                chat_models.sort(
                    key=lambda x: (
                        (0 if x.lower().startswith("gpt-5") else 1 if x.lower().startswith("gpt-4") else 2), x
                    ),
                    reverse=False,
                )
                logger.debug(f"Filtered chat completion models: {chat_models}")
                models = chat_models

            elif provider == APIProvider.GOOGLE:
                models_response = client.models.list()
                all_models = [m.id for m in models_response.data]
                logger.debug(f"All available GOOGLE models from API: {all_models}")
                gemini_models = [
                    m.id for m in models_response.data
                    if m.id.lower().startswith("gemini-") and "embedding" not in m.id.lower()
                ]
                def _rank(mid: str) -> tuple:
                    lm = mid.lower()
                    if "flash-8b" in lm: return (0, mid)
                    if "flash" in lm: return (1, mid)
                    if "pro" in lm: return (2, mid)
                    return (3, mid)
                gemini_models.sort(key=_rank)
                logger.debug(f"Filtered Gemini chat models: {gemini_models}")
                models = gemini_models

            elif provider == APIProvider.DEEPL:
                models_response = client.models.list()
                all_models = [m.id for m in models_response.data]
                logger.debug(f"All available DEEPL models from API: {all_models}")
                models = all_models or [get_deepl_identifier()]
            else:
                return [], ModelSource.ERROR.value

            # Cache the result for successful API calls (except temp API key usage)
            if source != ModelSource.API_TEMP_KEY:
                self._cache_models_and_persist(provider, models)
            return models, source.value

        except Exception as e:
            logger.error(f"Failed to fetch models from {provider.value}: {e}")
            return [], ModelSource.ERROR.value

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
