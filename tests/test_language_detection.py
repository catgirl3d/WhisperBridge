"""Tests for enhanced language detection."""

import pytest

from whisperbridge.utils.language_utils import (
    detect_language,
    detect_language_with_confidence,
    normalize_homoglyphs,
    detect_mixed_scripts
)

@pytest.mark.parametrize(
    ("text", "language", "mixed_scripts"),
    [
        ("I am currently investigating a users question", "en", False),
        ("Я сейчас исследую вопрос пользователя", "ru", False),
        ("Це дуже гарний програмний застосунок для перекладу", "ua", False),
        ("Im currently investigating а users question in Russian", "en", True),
        ("Hello мир and привет world", "en", True),
    ],
)
def test_detect_language_with_confidence_reports_language_and_scripts(text, language, mixed_scripts):
    result = detect_language_with_confidence(text)

    assert result.language == language
    assert result.mixed_scripts is mixed_scripts
    assert result.confidence > 0


def test_detect_language_wrapper_returns_detected_language():
    assert detect_language("Я зараз досліджую питання користувача") == "ua"


def test_normalize_homoglyphs_only_normalizes_latin_dominant_mixed_text():
    assert normalize_homoglyphs("Hello а world", aggressive=False) == "Hello a world"
    assert normalize_homoglyphs("Привет мир", aggressive=False) == "Привет мир"
    assert detect_mixed_scripts("Hello а world") is True


@pytest.mark.parametrize("text", ["", "   ", "123 !!!"])
def test_empty_or_non_letter_input_has_no_detected_language(text):
    result = detect_language_with_confidence(text)

    assert result.language is None
    assert result.confidence == 0.0
    assert detect_language(text) is None
