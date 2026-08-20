"""
Model token limits registry.

Defines maximum completion tokens for various AI models to prevent 'invalid_request_error'
due to exceeding model-specific limits.

Example API errors this prevents:
    # OpenAI BadRequestError:
    # openai.BadRequestError: Error code: 400
    # - 'messages': max_completion_tokens (65536) exceeds model limit (16384) for gpt-4o-mini
    
    # Google API error:
    # InvalidArgument: 400 Requested max_output_tokens (65536) exceeds model limit (8192) for gemini-1.5-pro

Updated with verified limits as of January 2026 based on official provider documentation.
"""

from typing import Dict, Optional
from loguru import logger

# Model token limits (max_completion_tokens)
# Values reflect hard output limits (completion tokens only) from provider documentation.
# Context window and output limit are separate constraints.
MODEL_TOKEN_LIMITS: Dict[str, int] = {
    # OpenAI Models
    "gpt-4o-mini": 16384,
    "gpt-4o": 16384,
    "gpt-4-turbo": 4096,
    "gpt-4-turbo-preview": 4096,
    "gpt-4": 4096,
    "gpt-4-32k": 4096,
    # Current documented models (OpenAI API docs, 2026)
    # https://developers.openai.com/api/docs/models/gpt-5.4-mini
    # https://developers.openai.com/api/docs/models/gpt-5.6-luna
    "gpt-5.4-mini": 128000,
    "gpt-5.6-luna": 128000,

    # Legacy GPT-5 family entries retained for saved/manual model IDs
    "gpt-5": 128000,        # Official output limit (400K context window)
    "gpt-5-mini": 128000,   # Same output limit as base GPT-5
    "gpt-5-nano": 32768,    # Verified lower-tier variant limit
    "gpt-5.2": 128000,      # Dec 2025 refresh (400K context window)
    
    # Google Gemini Models
    "gemini-1.5-flash": 8192,
    "gemini-1.5-pro": 8192,
    "gemini-1.5-flash-8b": 8192,
    "gemini-2.0-flash": 8192,
    "gemini-2.5-flash": 65536,  # Updated: Supports 64K output (Nov 2025)
    "gemini-2.5-pro": 65536,    # Updated: Supports 64K output (Nov 2025)
    "gemini-pro": 2048,
    "gemini-pro-vision": 2048,
    
    # Gemini 3 Series (Released Nov-Dec 2025)
    "gemini-3": 65536,          # Base identifier fallback
    "gemini-3-flash": 65536,    # Official output limit (1M context window)
    "gemini-3-pro": 65536,      # Official output limit (1M context window)
    "gemini-3-ultra": 65536,    # Verified output limit (1M context window)
}

# Safe default for unknown models (conservative value)
DEFAULT_MAX_COMPLETION_TOKENS = 4096

def get_model_max_completion_tokens(model: Optional[str]) -> int:
    """
    Get the maximum completion tokens for a given model.
    
    Args:
        model: Model name (e.g., "gpt-4o-mini", "gemini-3-pro")
    
    Returns:
        Hard registered output cap for the model, or safe default if unknown.
    """
    if not model:
        return DEFAULT_MAX_COMPLETION_TOKENS
        
    model_lower = model.lower().strip()
    
    # Exact match check
    if model_lower in MODEL_TOKEN_LIMITS:
        return MODEL_TOKEN_LIMITS[model_lower]
    
    # Prefix matching for model families (e.g., "gpt-5-turbo-012026" matches "gpt-5")
    # Sort keys by length descending to guarantee longest prefix match is found first
    for known_prefix in sorted(MODEL_TOKEN_LIMITS.keys(), key=len, reverse=True):
        if model_lower.startswith(known_prefix.lower()):
            return MODEL_TOKEN_LIMITS[known_prefix]
    
    logger.warning(f"Unknown model '{model}', using default max_completion_tokens={DEFAULT_MAX_COMPLETION_TOKENS}")
    return DEFAULT_MAX_COMPLETION_TOKENS
