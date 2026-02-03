"""
Google Generative AI chat client adapter for WhisperBridge.

Provides a minimal OpenAI-compatible surface for Gemini chat models so that
existing translation pipelines can reuse the same request code path.
"""

import base64
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple


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
        messages: List[Dict[str, Any]],
        temperature: float = 1.0,
        max_completion_tokens: int = 256,
        **kwargs: Any,
    ) -> Any:
        # Detect if this is a multimodal request
        is_multimodal = self._is_multimodal_request(messages)
        
        if is_multimodal:
            return self._create_multimodal(model, messages, temperature, max_completion_tokens, **kwargs)
        else:
            return self._create_text_only(model, messages, temperature, max_completion_tokens, **kwargs)

    def _is_multimodal_request(self, messages: List[Dict[str, Any]]) -> bool:
        """Check if messages contain image content."""
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
        return False

    def _create_text_only(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 1.0,
        max_completion_tokens: int = 256,
        **kwargs: Any,
    ) -> Any:
        """Handle text-only chat completion requests."""
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
            config.thinking_config = self._types.ThinkingConfig(thinking_level=self._types.ThinkingLevel.LOW)

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

    def _create_multimodal(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 1.0,
        max_completion_tokens: int = 256,
        **kwargs: Any,
    ) -> Any:
        """Handle multimodal (text + image) completion requests."""
        # Parse messages to extract system instruction, text, and image data
        system_parts = []
        user_text_parts = []
        image_data = None
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            
            if role == "system":
                system_parts.append(str(content or ""))
            elif role == "user":
                if isinstance(content, list):
                    # OpenAI-style multimodal message
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                user_text_parts.append(part.get("text", ""))
                            elif part.get("type") == "image_url" and not image_data:
                                # Extract first image
                                image_url = part.get("image_url", {}).get("url", "")
                                try:
                                    image_data, mime_type = self._parse_data_url(image_url)
                                except ValueError as e:
                                    raise ValueError(f"Failed to decode image data URL: {e}")
                elif isinstance(content, str):
                    user_text_parts.append(content)

        system_instruction = " ".join(system_parts).strip() or None
        prompt = " ".join(user_text_parts).strip() or "Describe this image"
        
        if not image_data:
            raise ValueError("No valid image data found in multimodal request")

        # Configure generation parameters
        config = self._types.GenerateContentConfig(
            max_output_tokens=int(max_completion_tokens or 256),
            temperature=float(temperature if temperature is not None else 1.0),
            system_instruction=system_instruction,
        )

        # Add ThinkingConfig for Gemini 3 models
        if model.startswith("gemini-3"):
            config.thinking_config = self._types.ThinkingConfig(thinking_level=self._types.ThinkingLevel.LOW)

        # Build multimodal content with text and image
        contents = [
            prompt,
            self._types.Part.from_bytes(data=image_data, mime_type=mime_type)
        ]

        # Generate content with new SDK
        response = self._client.models.generate_content(
            model=model,
            contents=contents,
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

    def _parse_data_url(self, data_url: str) -> Tuple[bytes, str]:
        """Parse a data URL and return the decoded bytes and MIME type.
        
        Supports formats like:
        - data:image/jpeg;base64,/9j/4AAQ...
        - data:image/png;base64,iVBORw0KG...
        - data:image/webp;base64,UklGR...
        
        Security:
        - Maximum size limit: 10MB (prevents memory exhaustion attacks)
        - Strict base64 validation
        - Exact pattern matching with regex anchors
        
        Args:
            data_url: The data URL string to parse.
            
        Returns:
            A tuple of (decoded_bytes, mime_type).
            
        Raises:
            ValueError: If the URL format is invalid, unsupported, or exceeds size limits.
        """
        # Size limit to prevent DoS attacks (10MB)
        MAX_DATA_URL_SIZE = 10 * 1024 * 1024
        
        if len(data_url) > MAX_DATA_URL_SIZE:
            raise ValueError(f"Data URL exceeds maximum size of {MAX_DATA_URL_SIZE} bytes")
        
        # Match data URL pattern with exact anchors (^ and $) for security
        # Pattern: data:[<mediatype>][;base64],<data>
        match = re.match(r'^data:([a-zA-Z0-9]+/[a-zA-Z0-9+.-]+);base64,(.+)$', data_url)
        if not match:
            raise ValueError("Invalid data URL format. Expected: data:<mime-type>;base64,<data>")
        
        mime_type = match.group(1)
        encoded_data = match.group(2)
        
        # Only accept image MIME types
        if not mime_type.startswith("image/"):
            raise ValueError(f"Unsupported MIME type: {mime_type}. Only image types are supported.")
        
        # Strict base64 decoding with validation
        try:
            decoded_data = base64.b64decode(encoded_data, validate=True)
        except Exception as e:
            raise ValueError(f"Failed to decode base64 data: {e}")
        
        # Verify decoded size is reasonable
        if len(decoded_data) > MAX_DATA_URL_SIZE:
            raise ValueError(f"Decoded image exceeds maximum size of {MAX_DATA_URL_SIZE} bytes")
        
        return decoded_data, mime_type

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