"""
Google Generative AI chat client adapter for WhisperBridge.

Provides a minimal OpenAI-compatible surface for Gemini chat models so that
existing translation pipelines can reuse the same request code path.
"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional


__all__ = ["GoogleChatClientAdapter"]


class GoogleChatClientAdapter:
    """
    Minimal adapter to mimic the OpenAI client's surface for Google Generative AI.

    Exposes:
      - chat.completions.create(...)
      - models.list()

    returning OpenAI-like response objects that the current pipeline expects.
    """

    def __init__(self, api_key: str, timeout: Optional[int] = None):
        try:
            import google.generativeai as genai  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency may be optional at runtime
            raise ImportError("google.generativeai is not installed") from exc

        genai.configure(api_key=api_key)
        self._genai = genai
        self._timeout = timeout
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
        model_obj = self._genai.GenerativeModel(model)

        system_text = " ".join(
            (message.get("content", "") for message in messages if message.get("role") == "system")
        ).strip()
        parts: List[str] = []
        if system_text:
            parts.append(f"System: {system_text}")
        for message in messages:
            role = message.get("role")
            if role in ("user", "assistant"):
                parts.append(str(message.get("content", "")))
        prompt = "\n\n".join(part for part in parts if part).strip() or "Hello"

        generation_config = {
            "max_output_tokens": int(max_completion_tokens or 256),
            "temperature": float(temperature or 1.0),
        }

        response = model_obj.generate_content(prompt, generation_config=generation_config)

        # Safely extract text from Gemini response
        # The .text property raises ValueError if response has no valid parts
        # (e.g., finish_reason=STOP with empty content)
        text = ""
        try:
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                finish_reason = getattr(candidate, 'finish_reason', None)
                # finish_reason 2 = SAFETY (blocked), 1 = STOP (normal)
                if finish_reason == 2:
                    # Response was blocked due to safety filters
                    text = ""
                elif hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    # Manually extract text from parts to avoid .text property issues
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text += part.text
                else:
                    # Fallback: try .text but may raise
                    text = response.text or ""
            else:
                text = response.text or ""
        except (ValueError, AttributeError) as e:
            # Handle "Invalid operation" when response has no valid parts
            # This happens when finish_reason=STOP but response is empty
            text = ""
        usage_metadata = getattr(response, "usage_metadata", None)
        total_tokens = 0
        if usage_metadata is not None:
            total_tokens = getattr(usage_metadata, "total_token_count", None) or (
                getattr(usage_metadata, "input_token_count", 0)
                + getattr(usage_metadata, "output_token_count", 0)
            )

        class _Message:
            pass

        class _Choice:
            pass

        class _Usage:
            pass

        class _Response:
            pass

        message = _Message()
        message.content = text

        choice = _Choice()
        choice.message = message

        usage = _Usage()
        usage.total_tokens = int(total_tokens or 0)

        mocked_response = _Response()
        mocked_response.choices = [choice]
        mocked_response.usage = usage
        return mocked_response

    def _list_models(self) -> Any:
        data = []
        for model in self._genai.list_models():
            model_name = getattr(model, "name", "")
            if "/" in model_name:
                model_name = model_name.split("/")[-1]
            supported_methods = set(getattr(model, "supported_generation_methods", []) or [])
            if "generateContent" in supported_methods and "embedding" not in model_name:
                model_info = SimpleNamespace()
                model_info.id = model_name
                data.append(model_info)
        return SimpleNamespace(data=data)