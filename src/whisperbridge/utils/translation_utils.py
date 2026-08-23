"""Translation utilities for WhisperBridge.

Prompt formatting, GPT response parsing, and token estimation helpers.
"""

from dataclasses import dataclass


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
