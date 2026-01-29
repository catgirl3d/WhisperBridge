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
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as exc:
            raise ImportError("google-genai is not installed") from exc

        # Configure HTTP options for timeout (SDK expects milliseconds)
        http_options = None
        if timeout:
            http_options = {"timeout": timeout * 1000}

        self._client = genai.Client(api_key=(api_key or "").strip(), http_options=http_options)
        self._types = types
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
        # Extract system instruction for native SDK support
        system_parts = [
            message.get("content", "")
            for message in messages
            if message.get("role") == "system"
        ]
        system_instruction = " ".join(system_parts).strip() or None

        # Build user/assistant content
        content_parts: List[str] = []
        for message in messages:
            role = message.get("role")
            if role in ("user", "assistant"):
                content_parts.append(str(message.get("content", "")))
        prompt = "\n\n".join(part for part in content_parts if part).strip() or "Hello"

        # Configure generation parameters
        config = self._types.GenerateContentConfig(
            max_output_tokens=int(max_completion_tokens or 256),
            temperature=float(temperature if temperature is not None else 1.0),
            system_instruction=system_instruction,
        )

        # Add ThinkingConfig for Gemini 3 models
        if model.startswith("gemini-3"):
            config.thinking_config = self._types.ThinkingConfig(thinking_level="low")

        # Generate content with new SDK
        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=config
        )

        # Extract text from new SDK response with safety handling
        text = self._extract_text(response)

        # Extract usage metadata
        usage_metadata = getattr(response, "usage_metadata", None)
        total_tokens = 0
        if usage_metadata is not None:
            total_tokens = getattr(usage_metadata, "total_token_count", None) or (
                getattr(usage_metadata, "input_token_count", 0)
                + getattr(usage_metadata, "output_token_count", 0)
            )

        # Create OpenAI-compatible response using SimpleNamespace
        message = SimpleNamespace(content=text)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(total_tokens=int(total_tokens or 0))
        response = SimpleNamespace(choices=[choice], usage=usage)
        return response

    def _extract_text(self, response: Any) -> str:
        """Extract text from SDK response with safety filter handling."""
        try:
            return response.text or ""
        except (ValueError, AttributeError):
            # Response blocked by safety filters, empty content, or missing attributes
            if hasattr(response, "candidates") and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                        for part in candidate.content.parts:
                            if hasattr(part, "text") and part.text:
                                return part.text
            return ""

    def _list_models(self) -> Any:
        data = []
        try:
            for model in self._client.models.list():
                model_name = getattr(model, "name", "")
                if "/" in model_name:
                    model_name = model_name.split("/")[-1]
                # Simplified filter: any Gemini-branded model that isn't for embeddings
                if model_name.lower().startswith("gemini-") and "embedding" not in model_name.lower():
                    model_info = SimpleNamespace()
                    model_info.id = model_name
                    data.append(model_info)
        except Exception as e:
            from loguru import logger
            logger.error(f"Error listing Gemini models: {e}")
        return SimpleNamespace(data=data)