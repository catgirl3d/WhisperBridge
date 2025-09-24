"""Language utilities for WhisperBridge.

Simple language detection and helpers.
"""

import re
from typing import Optional


def detect_language(text: str) -> Optional[str]:
    """Simple language detection based on character patterns."""
    if not text or not text.strip():
        return None

    text = text.strip().lower()

    # --- Prioritize Cyrillic languages ---

    # 1. Most reliable: check for unique Ukrainian characters
    if re.search(r"[ієїґ]", text):
        return "ua"

    # 2. Check for unique Russian characters
    if re.search(r"[ыъё]", text):
        return "ru"

    # 3. Strong Ukrainian signal: apostrophe usage before iotated vowels (я, ю, є, ї)
    #    Examples: п’ять, зв’язок, об’єкт, з’їсти
    #    We match Cyrillic consonant + apostrophe (’ or ') + [яюєї]
    if re.search(r"[бвгґджзйклмнпрстфхцчшщ][’'][яюєїї]", text):
        return "ua"

    # 3a. Check for common and Ukraine-specific words if specific chars are absent
    #     List focuses on lexemes frequent in Ukrainian and less likely in Russian.
    if re.search(
        r"\b(і|це|що|щоб|щодо|як|він|вона|але|був|була|було|ми|ви|ти|цей|його|вони|буде|саме|"
        r"також|бо|аби|вже|зараз|вчора|позавчора|завжди|ніколи|сьогодні|нині|щоби|потім|"
        r"жоден|жодна|жодне|жодної|жодного|жодних|кожен|кожна|кожне|кожні|"
        r"усього|усіх|усі|усім|усьому|усе|уся|усякий|усяка|усякі|"
        r"який|яка|яке|які|якийсь|якась|якесь|якісь|котрий|котра|котре|котрі|"
        r"куди|коли|звідки|навіщо|чому|оскільки|позаяк|тому|"
        r"дякую|будьмо|"
        r"пане|пані|отже|ось|хай|певно|напевно|власне|звичайно|наразі|завдяки|краще|легше|лише|надто|таки|"
        r"щонай|щонайменше|щойно|зовсім|щоправда|щотижня|щодня|щомісяця|щороку|ще|"
        r"наприклад|треба|можна|немає|нема|взагалі|загалом|зокрема|принаймні|усередині|назовні|"
        r"застосунок|додаток|налаштування|користувач|завантажити|зберегти|світлина|крамниця|"
        r"або|тобто|та|чи|хоч|хоча|однак|нехай|отож|адже|бодай|зрештою|одразу|тощо|"
        r"уздовж|вздовж|навколо|довкола|мережа|пошта|вимкнути|життя|завгодно|зручно|шлях|забагато|небагато|"
        r"радше|корисно|майно|власник|рахунок|гривня|решта|ласкаво|хтось|щось|кудись|колись|поки|доки|"
        r"перепрошую|гарно|згодом|дарма|"
        r"досить|обов[’']язково|ледве|швидко|гучно|проте|"
        r"той|чий|чия|програма|безпека|робота|праця)\b",
        text,
    ):
        return "ua"

    # 3b. Check for characteristic Ukrainian phrases and hyphenated forms
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
        text,
    ):
        return "ua"

    # 4. Check for common Russian words and general Cyrillic
    if re.search(r"\b(что|как|он|она|но|да|для|это|был|была|было|мы|вы|ты|же|его|они|будет)\b", text) or re.search(
        r"[а-я]", text
    ):
        return "ru"

    # --- Latin-based languages ---

    # More specific English patterns (checked after Cyrillic)
    if re.search(
        r"\b(the|a|an|is|are|was|were|in|on|at|and|or|but|for|with|from|that|it|he|she|they|have|has|to|of|you|we|my|your|will|be|not)\b",
        text,
    ):
        return "en"

    # Chinese characters
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"

    # Japanese characters (Hiragana, Katakana, Kanji)
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", text):
        return "ja"

    # Korean characters
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"

    # Arabic characters
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"

    # Spanish common patterns
    if re.search(r"\b(el|la|los|las|es|son|está|están)\b", text):
        return "es"

    # French common patterns
    if re.search(r"\b(le|la|les|et|est|sont|dans|pour)\b", text):
        return "fr"

    # German common patterns
    if re.search(r"\b(der|die|das|und|ist|sind|in|für)\b", text):
        return "de"

    # Italian common patterns
    if re.search(r"\b(il|la|i|gli|le|e|è|sono|in|per)\b", text):
        return "it"

    # Portuguese common patterns
    if re.search(r"\b(o|a|os|as|e|é|são|em|para)\b", text):
        return "pt"

    # Default to English if no other language is detected
    return "en"


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
