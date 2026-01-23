"""
DeepL translation adapter for WhisperBridge.

Provides OpenAI-compatible surface for DeepL translation API.
"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger
from ..core.config import get_deepl_identifier

__all__ = ["DeepLClientAdapter"]


def _normalize_lang_code(code: Optional[str]) -> Optional[str]:
    """
    Normalize ISO language codes to DeepL expected format.
    - 'ua' -> 'UK' (Ukrainian)
    - 'en' -> 'EN'
    - 'ru' -> 'RU', 'de' -> 'DE', etc.
    - Pass through already-uppercased codes like 'EN-US'
    """
    if not code:
        return None
    c = code.strip()
    if not c or c.lower() == "auto":
        return None
    c = c.upper()
    if c == "UA":
        return "UK"
    return c


class DeepLClientAdapter:
    """
    Minimal adapter to mimic the OpenAI client's surface for DeepL.

    Exposes:
      - chat.completions.create(...)
      - models.list()

    returning OpenAI-like response objects that the current pipeline expects.
    """

    def __init__(self, api_key: str, timeout: Optional[int] = None, plan: str = "free"):
        if not api_key or not isinstance(api_key, str):
            raise ValueError("DeepL API key is required")
        self._api_key = api_key
        self._timeout = timeout or 30
        self._base_url = "https://api-free.deepl.com" if (plan or "free").lower() == "free" else "https://api.deepl.com"
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.models = SimpleNamespace(list=self._list_models)

    def _create(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_completion_tokens: int = 256,
        **kwargs: Any,
    ) -> Any:
        """
        Translate using DeepL API with an OpenAI-compatible interface.
        Only user messages are concatenated and sent as text for translation.
        """
        # Collect user content
        parts: List[str] = []
        for msg in messages or []:
            if (msg.get("role") or "").strip().lower() == "user":
                parts.append(str(msg.get("content", "")))
        text = "\n".join([p for p in parts if p]).strip()
        if not text:
            # Ensure non-empty text
            text = ""

        # Language params
        target_lang = _normalize_lang_code(kwargs.get("target_lang"))
        source_lang = _normalize_lang_code(kwargs.get("source_lang"))
        if not target_lang:
            # Default to English if not provided
            target_lang = "EN"

        # Prepare request headers (DeepL requires header-based auth as of November 2025)
        headers = {
            "Authorization": f"DeepL-Auth-Key {self._api_key}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # Prepare request data (no auth_key in body anymore)
        data = {
            "text": text,
            "target_lang": target_lang,
        }
        if source_lang:
            data["source_lang"] = source_lang

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/v2/translate", headers=headers, data=data)
                resp.raise_for_status()
                payload = resp.json()
            translations = payload.get("translations") or []
            translated_text = translations[0].get("text", "") if translations else ""
            detected = translations[0].get("detected_source_language", "") if translations else ""
            return self._mock_response(translated_text, detected)
        except Exception as e:
            logger.error(f"DeepL API request failed: {e}")
            raise

    def _mock_response(self, text: str, detected_lang: str) -> Any:
        message = SimpleNamespace(content=text)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(total_tokens=0)
        response = SimpleNamespace(choices=[choice], usage=usage)
        return response

    def _list_models(self) -> Any:
        # DeepL has no models; return a single pseudo-model for compatibility
        model_info = SimpleNamespace(id=get_deepl_identifier())
        return SimpleNamespace(data=[model_info])