"""
API Utilities for WhisperBridge.

This module provides utilities for working with translation APIs,
including request formatting, response validation, and language detection.
"""

import re
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from loguru import logger


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


def detect_language(text: str) -> Optional[str]:
    """Simple language detection based on character patterns."""
    if not text or not text.strip():
        return None

    text = text.strip().lower()

    # More specific English patterns
    if re.search(r'\b(the|a|an|is|are|was|were|in|on|at|and|or|but)\b', text):
        return "en"

    # Cyrillic characters (Russian, Ukrainian, etc.)
    if re.search(r'[а-яё]', text):
        return "ru"

    # Chinese characters
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"

    # Japanese characters (Hiragana, Katakana, Kanji)
    if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text):
        return "ja"

    # Korean characters
    if re.search(r'[\uac00-\ud7af]', text):
        return "ko"

    # Arabic characters
    if re.search(r'[\u0600-\u06ff]', text):
        return "ar"

    # Spanish common patterns
    if re.search(r'\b(el|la|los|las|es|son|está|están)\b', text):
        return "es"

    # French common patterns
    if re.search(r'\b(le|la|les|et|est|sont|dans|pour)\b', text):
        return "fr"

    # German common patterns
    if re.search(r'\b(der|die|das|und|ist|sind|in|für)\b', text):
        return "de"

    # Italian common patterns
    if re.search(r'\b(il|la|i|gli|le|e|è|sono|in|per)\b', text):
        return "it"

    # Portuguese common patterns
    if re.search(r'\b(o|a|os|as|e|é|são|em|para)\b', text):
        return "pt"

    # Default to English if no other language is detected
    return "en"


def get_language_name(code: str) -> str:
    """Get full language name from language code."""
    language_names = {
        "en": "English",
        "ru": "Russian",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "ar": "Arabic",
        "auto": "Auto-detect"
    }

    return language_names.get(code.lower(), code.upper())


def validate_language_code(code: str) -> bool:
    """Validate language code format."""
    if code.lower() == "auto":
        return True

    # ISO 639-1 format (2 letters)
    if len(code) == 2 and code.isalpha():
        return True

    # ISO 639-3 format (3 letters)
    if len(code) == 3 and code.isalpha():
        return True

    return False


def sanitize_text(text: str) -> str:
    """Sanitize text for API processing."""
    if not text:
        return ""

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text.strip())

    # Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

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


def parse_gpt_response(response_text: str) -> str:
    """Parse and clean GPT response text."""
    if not response_text:
        return ""

    # Remove common prefixes that GPT might add
    prefixes_to_remove = [
        "Translation:",
        "Translated text:",
        "Here's the translation:",
        "The translation is:"
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


def create_system_prompt_template(source_lang: str = "auto", target_lang: str = "en") -> str:
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


def validate_api_key_format(api_key: str) -> bool:
    """Validate OpenAI API key format."""
    if not api_key or not isinstance(api_key, str):
        return False

    # OpenAI API keys start with 'sk-'
    if not api_key.startswith('sk-'):
        return False

    # Should be reasonably long
    if len(api_key) < 20:
        return False

    # Should contain only valid characters
    if not re.match(r'^sk-[a-zA-Z0-9\-_]+$', api_key):
        return False

    return True