"""
Translation Service for WhisperBridge.

This module provides API integration for text translation with
error handling and synchronous processing.
"""

import threading
from typing import Optional

from loguru import logger
from tenacity import RetryError

from ..core.api_manager import get_api_manager
from ..services.config_service import config_service
from ..utils.language_utils import detect_language
from ..utils.translation_utils import (
    TranslationRequest,
    TranslationResponse,
    StyleRequest,
    format_translation_prompt,
    format_style_prompt,
    parse_gpt_response,
)
from ..core.config import get_deepl_identifier, requires_model_selection, is_llm_provider


class TranslationService:
    """Main translation service with API integration."""

    def __init__(self):
        self._api_manager = get_api_manager()

    @property
    def is_available(self) -> bool:
        """Check if translation is available for the currently configured provider."""
        return self._api_manager.has_current_provider()

    def _make_response(
        self,
        *,
        success: bool,
        translated_text: Optional[str] = None,
        error_message: Optional[str] = None,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        model: Optional[str] = None,
    ) -> TranslationResponse:
        """Create a standardized TranslationResponse."""
        return TranslationResponse(
            success=success,
            translated_text=translated_text or "",
            error_message=error_message or "",
            source_lang=source_lang or "",
            target_lang=target_lang or "",
            model=model or "",
        )

    def _get_active_model(self) -> str:
        """
        Gets the currently configured model based on the selected API provider.
        Dynamically constructs the model setting key (e.g., 'openai_model').
        """
        provider = config_service.get_setting("api_provider")
        if not provider:
            raise ValueError("API provider is not configured in settings.")

        # Providers without model selection (e.g., DeepL) use fixed identifier
        if not requires_model_selection(str(provider)):
            return get_deepl_identifier()

        model_setting_key = f"{provider.lower()}_model"
        model = config_service.get_setting(model_setting_key)

        if not model:
            raise ValueError(
                f"Model for provider '{provider}' is not configured. "
                f"Expected setting: '{model_setting_key}'"
            )

        return model

    def _determine_languages(self, text: str, ui_source_lang: Optional[str], ui_target_lang: Optional[str]) -> tuple[str, str]:
        """Determines the effective source and target languages for translation."""
        detected_lang = self.detect_language_sync(text) or "auto"

        settings = config_service.get_settings()
        swap_enabled = getattr(settings, "auto_swap_en_ru", False)

        # 1. Check for auto-swap feature
        if swap_enabled and detected_lang in ["en", "ru"]:
            source = detected_lang
            target = "ru" if detected_lang == "en" else "en"
            logger.debug(f"Applied auto-swap: {source} -> {target}")
            return source, target

        # 2. Use UI selection if auto-swap doesn't apply
        source = ui_source_lang or "auto"
        if source == "auto":
            source = detected_lang

        target = ui_target_lang or getattr(settings, "ui_target_language", "en")

        logger.debug(f"Languages determined from UI/settings: {source} -> {target}")
        return source, target

    def translate_text(
        self,
        text: str,
        ui_source_lang: Optional[str] = None,
        ui_target_lang: Optional[str] = None,
    ) -> TranslationResponse:
        """Translate text synchronously using API."""

        logger.info(f"Starting translation for text: '{text[:30]}...'")
        source_lang = ui_source_lang
        target_lang = ui_target_lang

        try:
            # Determine languages using the helper
            source_lang, target_lang = self._determine_languages(text, ui_source_lang, ui_target_lang)

            # Get the active model once
            intended_model = self._get_active_model()

            # Prepare and execute translation request
            current_settings = config_service.get_settings()
            request = TranslationRequest(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                system_prompt=current_settings.system_prompt,
                model=intended_model,
            )

            response = self._call_gpt_api(request)

            # Validate response
            if not response.success:
                logger.error(f"Invalid translation response format: {response}")
                raise ValueError("Invalid translation response format")

            return response

        except RetryError as e:
            # Unwrap the original exception from the RetryError
            original_error = e.last_attempt.exception()
            error_msg = str(original_error) if original_error else str(e)
            logger.error(f"Translation failed (retries exhausted): {error_msg}")
            return self._make_response(
                success=False,
                error_message=error_msg,
                source_lang=source_lang,
                target_lang=target_lang,
            )

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return self._make_response(
                success=False,
                error_message=str(e),
                source_lang=source_lang,
                target_lang=target_lang,
            )

    def style_text(
        self,
        text: str,
        style_name: str,
    ) -> TranslationResponse:
        """Rewrite text in a selected style using the same API pipeline as translation."""
        logger.info(f"Starting style rewrite for text: '{text[:30]}...' with style '{style_name}'")

        try:
            # Get the active model once
            intended_model = self._get_active_model()

            # Resolve style preset
            settings = config_service.get_settings()
            styles = getattr(settings, "text_styles", []) or []
            style_entry = None
            for s in styles:
                try:
                    if (s.get("name") or "").strip().lower() == style_name.strip().lower():
                        style_entry = s
                        break
                except Exception:
                    continue
            if not style_entry and styles:
                style_entry = styles[0]  # fallback to first preset if provided style not found
                logger.warning(f"Style '{style_name}' not found. Falling back to preset '{style_entry.get('name','')}'.")
                style_name = style_entry.get("name", style_name)
            if not style_entry:
                raise ValueError("No style presets configured. Please add styles in settings.")

            style_prompt = style_entry.get("prompt", "").strip()
            if not style_prompt:
                raise ValueError(f"Selected style '{style_name}' has empty prompt")

            request = StyleRequest(
                text=text,
                style_name=style_name,
                style_prompt=style_prompt,
                model=intended_model,
            )

            if not self._api_manager.is_initialized():
                raise RuntimeError("API manager not initialized")

            if not self._api_manager.has_clients():
                logger.info("No API clients configured; returning empty styled text")
                return self._make_response(
                    success=True,
                    translated_text="",
                    source_lang="style",
                    target_lang=style_name,
                    model=intended_model,
                )

            # Enforce "respond in the same language as input" policy for stylist mode
            detected_lang = self.detect_language_sync(text)
            language_policy_lines = [
                "Important language policy:",
                "- Detect the input language and return the rewritten text in the same language.",
                "- Do not translate into another language.",
                "- Output only the rewritten text without explanations.",
            ]
            if detected_lang:
                language_policy_lines.append(f"- Input language code: {detected_lang}. Respond in {detected_lang}.")

            language_policy = "\n".join(language_policy_lines)

            messages = [
                {"role": "system", "content": f"{style_prompt}\n\n{language_policy}"},
                {"role": "user", "content": format_style_prompt(request)},
            ]

            response, final_model = self._api_manager.make_translation_request(
                messages=messages, model_hint=intended_model
            )

            raw_text = response.choices[0].message.content
            styled_text = parse_gpt_response(raw_text).strip()

            return self._make_response(
                success=True,
                translated_text=styled_text,
                source_lang="style",
                target_lang=style_name,
                model=final_model,
            )

        except RetryError as e:
            # Unwrap the original exception from the RetryError
            original_error = e.last_attempt.exception()
            error_msg = str(original_error) if original_error else str(e)
            logger.error(f"Styling failed (retries exhausted): {error_msg}")
            return self._make_response(
                success=False,
                error_message=error_msg,
                source_lang="style",
                target_lang=style_name,
            )

        except Exception as e:
            logger.error(f"Styling failed: {e}")
            return self._make_response(
                success=False,
                error_message=str(e),
                source_lang="style",
                target_lang=style_name,
            )

    def detect_language_sync(self, text: str) -> Optional[str]:
        """Detect language of the input text synchronously."""
        try:
            return detect_language(text)
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return None

    def _call_gpt_api(self, request: TranslationRequest) -> TranslationResponse:
        """Make actual API call using the API manager's logic."""
        if not self._api_manager.is_initialized():
            raise RuntimeError("API manager not initialized")

        # The API manager now centralizes the logic for client availability.
        if not self._api_manager.has_clients():
            logger.info("No API clients configured; returning empty translation")
            return self._make_response(
                success=True,
                translated_text="",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                model=(request.model or ""),
            )

        try:
            # Determine provider and prepare request accordingly
            provider_name = (config_service.get_setting("api_provider") or "openai").strip().lower()

            if not is_llm_provider(provider_name):
                # Non-LLM flow (e.g., DeepL): no system prompts; send raw user text and pass langs explicitly
                messages = [
                    {"role": "user", "content": request.text},
                ]
                # Map 'auto' to None to let DeepL auto-detect
                source_arg = None if (request.source_lang or "auto") == "auto" else request.source_lang
                target_arg = request.target_lang

                response, final_model = self._api_manager.make_translation_request(
                    messages=messages,
                    model_hint=get_deepl_identifier(),
                    target_lang=target_arg,
                    source_lang=source_arg,
                )

                raw_text = response.choices[0].message.content
                translated_text = (raw_text or "").strip()
            else:
                # LLM flow (OpenAI/Google): use system prompt + formatted user prompt
                messages = [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": format_translation_prompt(request)},
                ]

                # Delegate provider selection, model adjustment, and API call to the manager
                response, final_model = self._api_manager.make_translation_request(
                    messages=messages, model_hint=request.model
                )

                # Extract translation from response
                raw_text = response.choices[0].message.content
                translated_text = parse_gpt_response(raw_text).strip()

            return self._make_response(
                success=True,
                translated_text=translated_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                model=final_model,
            )

        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise


# Global translation service instance
_translation_service: Optional[TranslationService] = None
_service_lock = threading.RLock()


def get_translation_service() -> TranslationService:
    """Get the global translation service instance."""
    global _translation_service
    with _service_lock:
        if _translation_service is None:
            _translation_service = TranslationService()
        return _translation_service
