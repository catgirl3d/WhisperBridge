"""
Tests for model limits registry.

Based on test_implementation_plan.md
Coverage Goal: ≥95% for model_limits.py
"""

import logging

import pytest

from whisperbridge.core.model_limits import (
    get_model_max_completion_tokens,
    calculate_dynamic_completion_tokens,
    MODEL_TOKEN_LIMITS,
    DEFAULT_MAX_COMPLETION_TOKENS
)


class TestGetModelMaxTokens:
    """Tests for model limit lookup behavior."""

    @pytest.mark.parametrize("model,expected_limit", [
        ("gpt-5.4-mini", 128000),
        ("gpt-5.6-luna", 128000),
        ("gemini-3-flash", 65536),
    ])
    def test_get_model_max_tokens_exact_match(self, model, expected_limit):
        """TC-ML-001: Exact model names should return correct limits."""
        assert get_model_max_completion_tokens(model) == expected_limit

    @pytest.mark.parametrize("model", ["gpt-5.4-mini", "gpt-5.6-luna"])
    def test_current_openai_models_have_explicit_limits(self, model):
        """Documented current OpenAI models have explicit registry entries."""
        assert model in MODEL_TOKEN_LIMITS


    @pytest.mark.parametrize("model,expected_base_limit", [
        ("gpt-5.6-luna-012026", 128000),     # Matches the current GPT family prefix
        ("gemini-3-flash-preview", 65536),   # Should match "gemini-3-flash"
        ("gpt-5.4-mini-2026-07-18", 128000), # Matches the current GPT family prefix
        ("o1-preview", 100000),              # Should match "o1-"
        ("o3-mini", 100000),                 # Should match "o3-"
    ])
    def test_get_model_max_tokens_prefix_match(self, model, expected_base_limit):
        """TC-ML-002: Model variants should match base model limits via prefix."""
        assert get_model_max_completion_tokens(model) == expected_base_limit

    def test_get_model_max_tokens_unknown(self):
        """TC-ML-003: Unknown models should return safe default."""
        assert get_model_max_completion_tokens("unknown-model-xyz") == DEFAULT_MAX_COMPLETION_TOKENS

    def test_get_model_max_tokens_unknown_logs_warning(self, loguru_caplog):
        """Unknown models should log a WARNING (not DEBUG)."""
        get_model_max_completion_tokens("unknown-model-xyz")
        
        # Verify WARNING was logged
        assert any("Unknown model" in record.message for record in loguru_caplog.records), \
            f"Expected 'Unknown model' in log messages, got: {[r.message for r in loguru_caplog.records]}"
        assert any(record.levelname == "WARNING" for record in loguru_caplog.records), \
            f"Expected WARNING level, got: {[r.levelname for r in loguru_caplog.records]}"

    @pytest.mark.parametrize("deprecated_model", [
        "legacy-chat-model",
        "deprecated-chat-model",
    ])
    def test_deprecated_models_return_default(self, deprecated_model):
        """Deprecated models should return default limit."""
        result = get_model_max_completion_tokens(deprecated_model)
        assert result == DEFAULT_MAX_COMPLETION_TOKENS

    @pytest.mark.parametrize("model", [
        "GPT-5.4-MINI",
        "gpt-5.4-mini",
        "GpT-5.4-MiNi",
        "  gpt-5.4-mini  ",  # With whitespace
    ])
    def test_get_model_max_tokens_case_insensitive(self, model):
        """TC-ML-004: Model lookup should be case-insensitive and strip whitespace."""
        assert get_model_max_completion_tokens(model) == 128000

    def test_gpt5_mini_variant_returns_expected_limit(self):
        """
        TC-ML-005: A GPT-5 mini variant should resolve to the expected limit.

        This is a representative prefix-match case for a GPT-5 mini variant.
        The stricter longest-prefix proof lives in TC-ML-005b below.
        """
        result = get_model_max_completion_tokens("gpt-5.4-mini-turbo-test")

        assert result == 128000

    def test_prefix_matching_longest_wins_different_limits(self, mocker):
        """
        TC-ML-005b: Verify longest prefix matching with different token limits.
        
        This test patches MODEL_TOKEN_LIMITS to have different limits for
        "gpt-5.4" (50000) and "gpt-5.4-mini" (100000). When querying
        "gpt-5.4-mini-turbo", it should match the longer prefix.
        
        This ensures the sorted-by-length iteration correctly finds the longest match.
        """
        # Create a test dict with different limits for nested prefixes
        test_limits = {
            "gpt-5.4": 50000,      # Shorter prefix, lower limit
            "gpt-5.4-mini": 100000,  # Longer prefix, higher limit
        }
        
        mocker.patch('whisperbridge.core.model_limits.MODEL_TOKEN_LIMITS', test_limits)
        result = get_model_max_completion_tokens("gpt-5.4-mini-turbo-test")
        
        # Should match "gpt-5.4-mini" (longest prefix), return 100000
        # NOT match "gpt-5.4" (shorter prefix), which would return 50000
        assert result == 100000, (
                f"Expected 100000 (from 'gpt-5.4-mini' prefix), got {result}. "
                "This indicates the shortest prefix was matched instead of the longest."
            )

    def test_get_model_max_tokens_empty_string(self):
        """TC-ML-006: Empty model string should return default."""
        result = get_model_max_completion_tokens("")
        assert result == DEFAULT_MAX_COMPLETION_TOKENS

    def test_get_model_max_tokens_none(self):
        """None model should return default."""
        result = get_model_max_completion_tokens(None)
        assert result == DEFAULT_MAX_COMPLETION_TOKENS

    def test_get_model_max_tokens_special_chars(self):
        """TC-ML-007: Models with special chars should be handled gracefully."""
        result = get_model_max_completion_tokens("gpt-5.4@beta#v2")
        # The versioned current-model prefix resolves to the registered limit.
        assert result == 128000

    def test_model_limits_registry_integrity(self):
        """TC-ML-008: All registered models should have positive integer limits."""
        for model, limit in MODEL_TOKEN_LIMITS.items():
            assert isinstance(limit, int), f"{model} has non-int limit"
            assert limit > 0, f"{model} has non-positive limit"
            assert limit <= 1_000_000, f"{model} limit seems unrealistic: {limit}"


class TestCalculateDynamicTokens:
    """Tests for dynamic completion token calculation."""

    def test_calculate_dynamic_tokens_basic(self):
        """TC-ML-009: Standard case for a model with a 10% safety margin."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-5.4-mini",
            min_output_tokens=2048,
            output_safety_margin=0.1
        )
        
        # Expected: 128000 * 0.9 = 115200 (with safety margin)
        assert 114000 <= result <= 116000

    def test_calculate_dynamic_tokens_min_floor(self):
        """TC-ML-010: min_output_tokens should always be enforced."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-5.4-mini",
            min_output_tokens=2048,
            output_safety_margin=0.99
        )
        
        # 128000 * 0.01 is below min_output_tokens, so the floor applies.
        assert result == 2048

    @pytest.mark.parametrize("safety_margin,expected_multiplier", [
        (0.0, 1.0),    # No safety margin
        (0.1, 0.9),    # 10% margin
        (0.5, 0.5),    # 50% margin
        (0.99, 0.01),  # Extreme margin
    ])
    def test_calculate_dynamic_tokens_safety_margins(self, safety_margin, expected_multiplier):
        """TC-ML-012: Different safety margins should proportionally reduce output."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-5.4-mini",  # 128000 limit
            min_output_tokens=100,
            output_safety_margin=safety_margin
        )
        
        expected = int(128000 * expected_multiplier)
        assert abs(result - expected) / expected < 0.05  # <5% error

    @pytest.mark.parametrize("invalid_margin", [-0.1, 1.0, 1.5, 100])
    def test_calculate_dynamic_tokens_invalid_safety_margin(self, invalid_margin):
        """TC-ML-013: Safety margin outside [0.0, 1.0) should raise ValueError."""
        with pytest.raises(ValueError, match="output_safety_margin must be between"):
            calculate_dynamic_completion_tokens(
                model="gpt-5.4-mini",
                output_safety_margin=invalid_margin
            )

    @pytest.mark.parametrize("invalid_min", [-100, 0, 200_000])
    def test_calculate_dynamic_tokens_invalid_min_output(self, invalid_min):
        """TC-ML-015: min_output_tokens must be positive and reasonable."""
        with pytest.raises(ValueError):
            calculate_dynamic_completion_tokens(
                model="gpt-5.4-mini",
                min_output_tokens=invalid_min
            )

    def test_calculate_dynamic_tokens_rejects_min_output_above_model_cap(self):
        """TC-ML-016: min_output_tokens above the model cap should raise ValueError."""
        with pytest.raises(ValueError, match="min_output_tokens.*cannot exceed model's max output limit"):
            calculate_dynamic_completion_tokens(
                model="gpt-5.4-mini",  # 128000 limit
                min_output_tokens=200000,  # Request more than model supports
                output_safety_margin=0.0
            )

    def test_calculate_dynamic_tokens_for_high_cap_model(self):
        """TC-ML-017: High-cap models should still return valid output tokens."""
        result = calculate_dynamic_completion_tokens(
            model="gemini-3-flash",
            min_output_tokens=2048
        )
        
        assert result == int(65536 * 0.9)

    def test_calculate_dynamic_tokens_unknown_model(self):
        """TC-ML-018: Unknown model should use DEFAULT_MAX_COMPLETION_TOKENS."""
        result = calculate_dynamic_completion_tokens(
            model="future-gpt-x"
        )
        
        # Should fall back to safe default
        expected_safe = int(DEFAULT_MAX_COMPLETION_TOKENS * 0.9)  # With margin
        assert abs(result - expected_safe) / expected_safe < 0.1

    def test_calculate_dynamic_tokens_logging(self, loguru_caplog):
        """TC-ML-020: Verify debug logging contains expected information."""
        # Set log level to DEBUG to capture debug messages
        loguru_caplog.set_level(logging.DEBUG)
        
        result = calculate_dynamic_completion_tokens(
            model="gpt-5.4-mini"
        )
        
        # Verify the function returns a valid result
        assert isinstance(result, int)
        assert result > 0
        
        # Verify that debug logging occurred
        assert len(loguru_caplog.records) > 0, "No debug logs were captured"
        
        # Verify the log message contains expected information
        log_messages = [record.message for record in loguru_caplog.records]
        assert any("Model: gpt-5.4-mini" in msg for msg in log_messages), \
            f"Expected log message containing 'Model: gpt-5.4-mini', got: {log_messages}"


class TestCalculateDynamicTokensValidation:
    """Additional validation tests"""

    def test_empty_model_string(self):
        """Empty model string should raise ValueError."""
        with pytest.raises(ValueError, match="model must be a non-empty string"):
            calculate_dynamic_completion_tokens(
                model=""
            )

    def test_none_model(self):
        """None model should raise ValueError."""
        with pytest.raises(ValueError, match="model must be a non-empty string"):
            calculate_dynamic_completion_tokens(model=None)

    def test_whitespace_only_model(self):
        """Whitespace-only model should raise ValueError."""
        with pytest.raises(ValueError, match="model must be a non-empty string"):
            calculate_dynamic_completion_tokens(
                model="   "
            )

    def test_default_min_output_tokens(self):
        """Test default min_output_tokens value."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-5.4-mini"
        )
        # Default min_output_tokens is 2048
        assert result >= 2048

    def test_default_output_safety_margin(self):
        """Test default output_safety_margin value."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-5.4-mini",
            min_output_tokens=100
        )
        # Default output_safety_margin is 0.1
        # Expected: 128000 * 0.9 = 115200
        assert 114000 <= result <= 116000
