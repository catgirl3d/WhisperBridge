"""Translation utilities for WhisperBridge.

Prompt formatting, GPT response parsing, translation response validation,
and token estimation helpers.
"""

import re
from dataclasses import dataclass

from loguru import logger

from .language_utils import detect_language, get_language_name


@dataclass
class TranslationRequest:
    """Request data for translation API."""

    text: str
    source_lang: str
    target_lang: str
    system_prompt: str
    model: str


@dataclass
class TranslationResponse:
    """Response data from translation API."""

    success: bool
    translated_text: str = ""
    source_lang: str = ""
    target_lang: str = ""
    model: str = ""
    error_message: str = ""
    tokens_used: int = 0
    cached: bool = False


@dataclass
class StyleRequest:
    """Request data for text styling (rewriting) API."""
    text: str
    style_name: str
    style_prompt: str
    model: str


def format_translation_prompt(request: TranslationRequest) -> str:
    """Format translation prompt for GPT API.

    Note: do not include a trailing 'Translation:' label so the model
    is not prompted to echo that label in its response.
    """
    if request.source_lang == "auto":
        prompt = f"""Translate the following text to {request.target_lang}.
If the source language is already {request.target_lang}, return the original text unchanged.

Text to translate:
{request.text}
"""
    else:
        prompt = f"""Translate the following text from {request.source_lang} to {request.target_lang}.

Text to translate:
{request.text}
"""
    return prompt


def format_style_prompt(request: StyleRequest) -> str:
    """Format user message for text styling.

    System prompt should contain the style instructions (request.style_prompt).
    The user content is the raw text (optionally with a minimal preface).
    """
    return f"""Text to rewrite:
{request.text}
"""


def validate_translation_response(response: TranslationResponse) -> bool:
    """Validate translation API response."""
    if not response.success:
        return False

    if not response.translated_text or not response.translated_text.strip():
        logger.warning("Empty translation response")
        return False

    if len(response.translated_text.strip()) < len(response.translated_text) * 0.1:
        logger.warning("Translation response too short compared to original")
        return False

    return True


def parse_gpt_response(response_text: str) -> str:
    """Parse and clean GPT response text."""
    if not response_text:
        return ""

    # Remove common prefixes that GPT might add
    prefixes_to_remove = [
        "Translation:",
        "Translated text:",
        "Here's the translation:",
        "The translation is:",
    ]

    text = response_text.strip()

    for prefix in prefixes_to_remove:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
            break

    # Remove quotes if the entire response is quoted
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    elif text.startswith("'") and text.endswith("'"):
        text = text[1:-1].strip()

    return text


def create_system_prompt_template(
    source_lang: str = "auto", target_lang: str = "en"
) -> str:
    """Create a customized system prompt template."""
    if source_lang == "auto":
        template = f"""You are a professional translator. Your task is to translate text accurately and naturally to {get_language_name(target_lang)}.

Guidelines:
- Maintain the original meaning and tone
- Use natural, fluent language
- Preserve formatting and structure when possible
- If the text is already in {get_language_name(target_lang)}, return it unchanged
- Only provide the translation, no additional explanations

Translate the following text:"""
    else:
        template = f"""You are a professional translator. Your task is to translate text from {get_language_name(source_lang)} to {get_language_name(target_lang)} accurately and naturally.

Guidelines:
- Maintain the original meaning and tone
- Use natural, fluent {get_language_name(target_lang)}
- Preserve formatting and structure when possible
- Only provide the translation, no additional explanations

Translate the following text:"""

    return template


def sanitize_text(text: str) -> str:
    """Sanitize text for API processing."""
    if not text:
        return ""

    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text.strip())

    # Remove control characters
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

    return text


def estimate_tokens(text: str) -> int:
    """Estimate token count for text (rough approximation)."""
    if not text:
        return 0

    # Rough approximation: 1 token ≈ 4 characters for English
    # Adjust for other languages
    char_count = len(text)

    # For languages with more complex characters, adjust ratio
    if detect_language(text) in ["zh", "ja", "ko"]:
        return max(1, char_count // 2)  # More tokens per character for CJK

    return max(1, char_count // 4)


def format_error_message(error: Exception) -> str:
    """Format error message for user display."""
    error_type = type(error).__name__

    if "API" in error_type:
        return "API request failed. Please check your internet connection and API key."
    elif "timeout" in str(error).lower():
        return "Request timed out. Please try again."
    elif "rate" in str(error).lower():
        return "API rate limit exceeded. Please wait and try again."
    elif "quota" in str(error).lower():
        return "API quota exceeded. Please check your account limits."
    else:
        return f"Translation failed: {str(error)}"
