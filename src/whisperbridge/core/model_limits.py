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
# Values reflect HARD OUTPUT LIMITS (completion tokens only) per official API docs (Jan 2026)
# Critical distinction: Context window ≠ output limit (e.g., Gemini 3 has 1M context but 64K output cap)
MODEL_TOKEN_LIMITS: Dict[str, int] = {
    # OpenAI Models
    "gpt-4o-mini": 16384,
    "gpt-4o": 16384,
    "gpt-4-turbo": 4096,
    "gpt-4-turbo-preview": 4096,
    "gpt-4": 4096,
    "gpt-4-32k": 4096,
    "o1-": 100000,  # Reasoning models (output-focused)
    "o3-": 100000,
    
    # GPT-5 Series (Released Aug 2025 - Dec 2025)
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

# Safe minimum output tokens to reserve for responses
# Ensures the model has enough capacity to provide a meaningful answer
DEFAULT_MIN_OUTPUT_TOKENS = 2048


def get_model_max_completion_tokens(model: Optional[str]) -> int:
    """
    Get the maximum completion tokens for a given model.
    
    Args:
        model: Model name (e.g., "gpt-4o-mini", "gemini-3-pro")
    
    Returns:
        Maximum completion tokens for the model, or safe default if unknown.
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


def calculate_dynamic_completion_tokens(
    model: Optional[str],
    min_output_tokens: int = DEFAULT_MIN_OUTPUT_TOKENS,
    output_safety_margin: float = 0.1  # Reserve 10% of output limit for API calculation variance
) -> int:
    """
    Calculate dynamic max_completion_tokens based on model limits.
    
    Prevents 'invalid_request_error' by respecting hard output limits while reserving
    buffer for provider calculation variances.
    
    Args:
        model: Model identifier
        min_output_tokens: Absolute minimum tokens to reserve for response
        output_safety_margin: Reserve 10% of output limit for API calculation variance
    
    Returns:
        Safe max_completion_tokens value for API request
    """
    # Validate model parameter
    if not model or not model.strip():
        raise ValueError("model must be a non-empty string")
    
    # Validate output_safety_margin
    if not (0.0 <= output_safety_margin < 1.0):
        raise ValueError("output_safety_margin must be between 0.0 and 1.0")
    
    max_model_output = get_model_max_completion_tokens(model)
    
    # Validate min_output_tokens after we know the model's limit
    if min_output_tokens <= 0:
        raise ValueError("min_output_tokens must be positive (greater than 0)")
    if min_output_tokens > max_model_output:
        raise ValueError(
            f"min_output_tokens ({min_output_tokens}) cannot exceed model's max output limit "
            f"({max_model_output} for '{model}')"
        )
    
    # Apply output safety margin to model's hard output limit
    # Modern APIs (GPT-5, Gemini 3) have separate input/output limits, so output capacity
    # is independent of input size.
    available_output = int(max_model_output * (1.0 - output_safety_margin))
    
    # Ensure minimum useful output while respecting absolute model cap
    calculated = max(min_output_tokens, available_output)
    final_tokens = min(calculated, max_model_output)
    
    logger.debug(
        f"Model: {model}, "
        f"Output limit: {max_model_output}, Available: {available_output}, Final tokens: {final_tokens}"
    )
    return final_tokens
