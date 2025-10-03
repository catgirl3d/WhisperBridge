"""Language utilities for WhisperBridge.

Enhanced language detection with homoglyph handling and confidence scoring.
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict, Tuple


@dataclass
class LanguageDetectionResult:
    """Result of language detection with confidence score.
    
    Attributes:
        language: Detected language code (e.g., 'en', 'ru', 'ua') or None if detection failed
        confidence: Confidence score from 0.0 to 1.0
        mixed_scripts: Whether text contains mixed writing systems (homoglyphs suspected)
    """
    language: Optional[str]
    confidence: float
    mixed_scripts: bool = False


# Homoglyph mapping: Cyrillic -> Latin
HOMOGLYPH_MAP: Dict[str, str] = {
    'а': 'a', 'А': 'A',
    'с': 'c', 'С': 'C',
    'е': 'e', 'Е': 'E',
    'о': 'o', 'О': 'O',
    'р': 'p', 'Р': 'P',
    'х': 'x', 'Х': 'X',
    'у': 'y', 'У': 'Y',
    'в': 'B', 'В': 'B',  # Cyrillic 'в' can look like Latin 'B'
    'к': 'k', 'К': 'K',
    'м': 'm', 'М': 'M',
    'н': 'H', 'Н': 'H',  # Cyrillic 'н' can look like Latin 'H'
    'т': 'T', 'Т': 'T',
}


def normalize_homoglyphs(text: str, aggressive: bool = False) -> str:
    """Replace visually similar Cyrillic characters with Latin equivalents.
    
    Args:
        text: Input text to normalize
        aggressive: If True, normalize all homoglyphs. If False, only normalize in Latin context
        
    Returns:
        Normalized text with homoglyphs replaced
    """
    if not text:
        return text
    
    # If not aggressive, check if text is predominantly Latin before normalizing
    if not aggressive:
        latin_chars = len(re.findall(r'[a-zA-Z]', text))
        cyrillic_chars = len(re.findall(r'[а-яА-ЯёЁіїєґІЇЄҐ]', text))
        total_letters = latin_chars + cyrillic_chars
        
        if total_letters == 0:
            return text
        
        # Only normalize if Latin is dominant (>70%)
        if latin_chars / total_letters < 0.7:
            return text
    
    # Apply homoglyph normalization
    result = text
    for cyr, lat in HOMOGLYPH_MAP.items():
        result = result.replace(cyr, lat)
    
    return result


def count_script_characters(text: str) -> Dict[str, int]:
    """Count characters from different writing systems.
    
    Args:
        text: Input text to analyze
        
    Returns:
        Dictionary with counts for different character types
    """
    if not text:
        return {}
    
    text_lower = text.lower()
    
    return {
        'latin': len(re.findall(r'[a-z]', text_lower)),
        'cyrillic': len(re.findall(r'[а-яё]', text_lower)),
        'cyrillic_ua_specific': len(re.findall(r'[іїєґ]', text_lower)),
        'cyrillic_ru_specific': len(re.findall(r'[ыъё]', text_lower)),
        'chinese': len(re.findall(r'[\u4e00-\u9fff]', text_lower)),
        'japanese': len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text_lower)),
        'korean': len(re.findall(r'[\uac00-\ud7af]', text_lower)),
        'arabic': len(re.findall(r'[\u0600-\u06ff]', text_lower)),
    }


def detect_mixed_scripts(text: str) -> bool:
    """Detect if text contains mixed writing systems (potential homoglyphs).
    
    Args:
        text: Input text to analyze
        
    Returns:
        True if text contains characters from multiple scripts
    """
    counts = count_script_characters(text)
    
    has_latin = counts.get('latin', 0) > 0
    has_cyrillic = counts.get('cyrillic', 0) > 0
    
    # Mixed Latin and Cyrillic is suspicious
    return has_latin and has_cyrillic


def detect_language_with_confidence(text: str, normalize: bool = True) -> LanguageDetectionResult:
    """Enhanced language detection with confidence scoring and homoglyph handling.
    
    Args:
        text: Input text to analyze
        normalize: Whether to normalize homoglyphs before detection
        
    Returns:
        LanguageDetectionResult with detected language, confidence, and metadata
    """
    if not text or not text.strip():
        return LanguageDetectionResult(language=None, confidence=0.0)
    
    original_text = text
    text = text.strip().lower()
    
    # Check for mixed scripts (potential homoglyphs)
    mixed_scripts = detect_mixed_scripts(text)
    
    # Normalize homoglyphs if requested and mixed scripts detected
    if normalize and mixed_scripts:
        text = normalize_homoglyphs(text, aggressive=False)
    
    # Count characters from different scripts
    counts = count_script_characters(text)
    total_letters = sum(counts.values())
    
    if total_letters == 0:
        return LanguageDetectionResult(language=None, confidence=0.0)
    
    # Calculate script ratios
    cyrillic_ratio = (counts.get('cyrillic', 0) +
                      counts.get('cyrillic_ua_specific', 0) +
                      counts.get('cyrillic_ru_specific', 0)) / total_letters
    latin_ratio = counts.get('latin', 0) / total_letters
    
    # Language detection with weighted scoring
    scores: Dict[str, float] = {}
    
    # --- Cyrillic languages ---
    
    # Ukrainian: High weight for unique characters
    if counts.get('cyrillic_ua_specific', 0) > 0:
        # Very strong signal from unique Ukrainian letters
        scores['ua'] = 0.9 + (counts['cyrillic_ua_specific'] / total_letters) * 0.1
    
    # Russian: High weight for unique characters
    if counts.get('cyrillic_ru_specific', 0) > 0:
        scores['ru'] = 0.85 + (counts['cyrillic_ru_specific'] / total_letters) * 0.15
    
    # Ukrainian: apostrophe patterns (strong signal)
    if re.search(r"[бвгґджзйклмнпрстфхцчшщ][''][яюєїї]", text):
        scores['ua'] = max(scores.get('ua', 0), 0.85)
    
    # Ukrainian: common words (strong signal, high weight)
    ua_word_matches = len(re.findall(
        r"\b(і|це|що|щоб|щодо|як|він|вона|але|був|була|було|ми|ви|ти|цей|його|вони|буде|саме|"
        r"також|бо|аби|вже|зараз|вчора|позавчора|завжди|ніколи|сьогодні|нині|щоби|потім|"
        r"жоден|жодна|жодне|жодної|жодного|жодних|кожен|кожна|кожне|кожні|"
        r"усього|усіх|усі|усім|усьому|усе|уся|усякий|усяка|усякі|"
        r"який|яка|яке|які|якийсь|якась|якесь|якісь|котрий|котра|котре|котрі|"
        r"куди|коли|звідки|навіщо|чому|оскільки|позаяк|тому|дякую|будьмо|"
        r"пане|пані|отже|ось|хай|певно|напевно|власне|звичайно|наразі|завдяки|краще|легше|лише|надто|таки|"
        r"щонай|щонайменше|щойно|зовсім|щоправда|щотижня|щодня|щомісяця|щороку|ще|"
        r"наприклад|треба|можна|немає|нема|взагалі|загалом|зокрема|принаймні|усередині|назовні|"
        r"застосунок|додаток|налаштування|користувач|завантажити|зберегти|світлина|крамниця|"
        r"або|тобто|та|чи|хоч|хоча|однак|нехай|отож|адже|бодай|зрештою|одразу|тощо|"
        r"уздовж|вздовж|навколо|довкола|мережа|пошта|вимкнути|життя|завгодно|зручно|шлях|забагато|небагато|"
        r"радше|корисно|майно|власник|рахунок|гривня|решта|ласкаво|хтось|щось|кудись|колись|поки|доки|"
        r"перепрошую|гарно|згодом|дарма|досить|обов['']язково|ледве|швидко|гучно|проте|"
        r"той|чий|чия|програма|безпека|робота|праця)\b",
        text
    ))
    if ua_word_matches > 0:
        # Each word match adds to confidence (very strong signal)
        word_score = min(0.95, 0.7 + (ua_word_matches * 0.05))
        scores['ua'] = max(scores.get('ua', 0), word_score)
    
    # Ukrainian: characteristic phrases (strong signal)
    if re.search(
        r"(?:\bбудь\s+ласка\b|\bтаким\s+чином\b|\bдо\s+речі\b|\bврешті(?:-|\s+)решт\b|\bпід\s+час\b|"
        r"\bз\s+огляду\s+на\b|\bнезважаючи\s+на\b|\bна\s+відміну\s+від\b|\bпо\s+суті\b|"
        r"\bбудь(?:-|\s+)що\b|\bбудь(?:-|\s+)хто\b|\bбудь(?:-|\s+)де\b|\bбудь(?:-|\s+)як\b|\bбудь(?:-|\s+)коли\b|"
        r"\bбудь(?:-|\s+)який\b|\bбудь(?:-|\s+)яка\b|\bбудь(?:-|\s+)яке\b|\bбудь(?:-|\s+)які\b|"
        r"\bбудь(?:-|\s+)якого\b|\bбудь(?:-|\s+)якої\b|\bбудь(?:-|\s+)якому\b|\bбудь(?:-|\s+)яким\b|\bбудь(?:-|\s+)яких\b|\bбудь(?:-|\s+)якою\b|"
        r"\bпо(?:-|\s+)перше\b|\bпо(?:-|\s+)друге\b|\bпо(?:-|\s+)третє\b|"
        r"\bбудь\s*ласка\b|\bтаким\s*чином\b|\bдо\s*речи\b|\bврешти\s*решт\b|\bпид\s*час\b|"
        r"\bз\s*огляду\s*на\b|\bнезважаючи\s*на\b|\bза\s*винятком\b|\bу\s*рази\b|\bна\s*щастя\b|\bтим\s*не\s*менш\b|\bна\s*мою\s*думку\b|"
        r"\bпо\s*перше\b|\bпо\s*друге\b|\bпо\s*третє\b)",
        text
    ):
        scores['ua'] = max(scores.get('ua', 0), 0.9)
    
    # Russian: common words (strong signal but lower than Ukrainian specifics)
    ru_word_matches = len(re.findall(
        r"\b(что|как|он|она|но|да|для|это|был|была|было|мы|вы|ты|же|его|они|будет)\b",
        text
    ))
    if ru_word_matches > 0:
        word_score = min(0.8, 0.6 + (ru_word_matches * 0.04))
        scores['ru'] = max(scores.get('ru', 0), word_score)
    
    # General Cyrillic detection (low confidence if no specific markers)
    if cyrillic_ratio >= 0.3 and 'ua' not in scores and 'ru' not in scores:
        # Require significant Cyrillic presence to avoid false positives from homoglyphs
        scores['ru'] = 0.4 + (cyrillic_ratio * 0.3)
    
    # --- Latin-based languages ---
    
    # English: common words (high weight)
    en_word_matches = len(re.findall(
        r"\b(the|an|am|is|are|was|were|in|on|at|and|or|but|for|with|from|that|it|he|she|they|have|has|to|of|you|we|my|your|will|be|not|can|just|only|very|also|even|more|most|much|many|some|such|any|his|this|which|would|should|could|their|these|those|about|into|over|between|before|after|because|while|though|through|without|within|across|around)\b",
        text
    ))
    if en_word_matches > 0:
        word_score = min(0.9, 0.65 + (en_word_matches * 0.05))
        scores['en'] = max(scores.get('en', 0), word_score)
    
    # If predominantly Latin without English words, still give English a score
    if latin_ratio >= 0.7 and 'en' not in scores:
        scores['en'] = 0.5 + (latin_ratio * 0.2)
    
    # --- Other languages ---
    
    # Chinese
    if counts.get('chinese', 0) > 0:
        chinese_ratio = counts['chinese'] / total_letters
        scores['zh'] = 0.8 + (chinese_ratio * 0.2)
    
    # Japanese
    if counts.get('japanese', 0) > 0:
        japanese_ratio = counts['japanese'] / total_letters
        scores['ja'] = 0.8 + (japanese_ratio * 0.2)
    
    # Korean
    if counts.get('korean', 0) > 0:
        korean_ratio = counts['korean'] / total_letters
        scores['ko'] = 0.8 + (korean_ratio * 0.2)
    
    # Arabic
    if counts.get('arabic', 0) > 0:
        arabic_ratio = counts['arabic'] / total_letters
        scores['ar'] = 0.8 + (arabic_ratio * 0.2)
    
    # Spanish
    if re.search(r"\b(el|la|los|las|es|son|está|están)\b", text):
        scores['es'] = 0.7
    
    # French
    if re.search(r"\b(le|la|les|et|est|sont|dans|pour)\b", text):
        scores['fr'] = 0.7
    
    # German
    if re.search(r"\b(der|die|das|und|ist|sind|in|für)\b", text):
        scores['de'] = 0.7
    
    # Italian
    if re.search(r"\b(il|la|i|gli|le|e|è|sono|in|per)\b", text):
        scores['it'] = 0.7
    
    # Portuguese
    if re.search(r"\b(o|a|os|as|e|é|são|em|para)\b", text):
        scores['pt'] = 0.7
    
    # Determine best match
    if not scores:
        # Default to English if no other detection
        return LanguageDetectionResult(
            language='en',
            confidence=0.3,
            mixed_scripts=mixed_scripts
        )
    
    best_lang = max(scores.items(), key=lambda x: x[1])
    detected_language = best_lang[0]
    confidence = best_lang[1]
    
    # Reduce confidence if mixed scripts detected (potential homoglyphs)
    if mixed_scripts and detected_language in ('en', 'ru', 'ua'):
        confidence *= 0.85
    
    return LanguageDetectionResult(
        language=detected_language,
        confidence=min(1.0, confidence),
        mixed_scripts=mixed_scripts
    )


def detect_language(text: str) -> Optional[str]:
    """Detect language from text (backward compatible wrapper).
    
    This function provides backward compatibility with existing code.
    For new code, consider using detect_language_with_confidence() instead.
    
    Args:
        text: Input text to analyze
        
    Returns:
        Language code (e.g., 'en', 'ru', 'ua') or None if detection failed
    """
    result = detect_language_with_confidence(text, normalize=True)
    
    # Return None if confidence is too low (< 0.4) to avoid false positives
    if result.confidence < 0.4:
        return None
    
    return result.language


def get_language_name(code: str) -> str:
    """Get full language name from language code."""
    language_names = {
        "en": "English",
        "ru": "Russian",
        "ua": "Ukrainian",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "ar": "Arabic",
        "auto": "Auto-detect",
    }

    return language_names.get(code.lower(), code.upper())


