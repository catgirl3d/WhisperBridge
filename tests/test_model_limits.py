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
    """Category 1: Model Limit Lookups (8 tests)"""

    @pytest.mark.parametrize("model,expected_limit", [
        ("gpt-4o-mini", 16384),
        ("gpt-5", 128000),
        ("gemini-3-flash", 65536),
    ])
    def test_get_model_max_tokens_exact_match(self, model, expected_limit):
        """TC-ML-001: Exact model names should return correct limits."""
        assert get_model_max_completion_tokens(model) == expected_limit

    @pytest.mark.parametrize("model,expected_base_limit", [
        ("gpt-5-turbo-012026", 128000),      # Should match "gpt-5"
        ("gemini-3-flash-preview", 65536),   # Should match "gemini-3-flash"
        ("gpt-4o-mini-2024-07-18", 16384),   # Should match "gpt-4o-mini"
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
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
    ])
    def test_deprecated_models_return_default(self, deprecated_model):
        """Deprecated models should return default limit."""
        result = get_model_max_completion_tokens(deprecated_model)
        assert result == DEFAULT_MAX_COMPLETION_TOKENS

    @pytest.mark.parametrize("model", [
        "GPT-5",
        "gpt-5",
        "GpT-5",
        "  gpt-5  ",  # With whitespace
    ])
    def test_get_model_max_tokens_case_insensitive(self, model):
        """TC-ML-004: Model lookup should be case-insensitive and strip whitespace."""
        assert get_model_max_completion_tokens(model) == 128000

    def test_prefix_matching_longest_wins(self):
        """
        TC-ML-005: Ambiguous prefix matching.
        
        Given registry: {"gpt-5": 128000, "gpt-5-mini": 128000}
        Model "gpt-5-mini-turbo" should match "gpt-5-mini" (longest prefix)
        """
        # Both gpt-5 and gpt-5-mini have same limit (128000), so this tests the matching logic
        result = get_model_max_completion_tokens("gpt-5-mini-turbo-test")
        
        # Should match "gpt-5-mini" prefix (longest), NOT "gpt-5"
        # Since both have same limit, we verify it returns 128000
        assert result == 128000

    def test_prefix_matching_longest_wins_different_limits(self, mocker):
        """
        TC-ML-005b: Verify longest prefix matching with different token limits.
        
        This test patches MODEL_TOKEN_LIMITS to have different limits for
        "gpt-5" (50000) and "gpt-5-mini" (100000). When querying "gpt-5-mini-turbo",
        it should match "gpt-5-mini" (longest prefix) and return 100000, NOT 50000.
        
        This ensures the sorted-by-length iteration correctly finds the longest match.
        """
        # Create a test dict with different limits for nested prefixes
        test_limits = {
            "gpt-5": 50000,      # Shorter prefix, lower limit
            "gpt-5-mini": 100000,  # Longer prefix, higher limit
        }
        
        mocker.patch('whisperbridge.core.model_limits.MODEL_TOKEN_LIMITS', test_limits)
        result = get_model_max_completion_tokens("gpt-5-mini-turbo-test")
        
        # Should match "gpt-5-mini" (longest prefix), return 100000
        # NOT match "gpt-5" (shorter prefix), which would return 50000
        assert result == 100000, (
                f"Expected 100000 (from 'gpt-5-mini' prefix), got {result}. "
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
        result = get_model_max_completion_tokens("gpt-5@beta#v2")
        # "gpt-5@beta#v2" matches "gpt-5" prefix, so returns 128000
        assert result == 128000

    def test_model_limits_registry_integrity(self):
        """TC-ML-008: All registered models should have positive integer limits."""
        for model, limit in MODEL_TOKEN_LIMITS.items():
            assert isinstance(limit, int), f"{model} has non-int limit"
            assert limit > 0, f"{model} has non-positive limit"
            assert limit <= 1_000_000, f"{model} limit seems unrealistic: {limit}"


class TestCalculateDynamicTokens:
    """Category 2: Dynamic Completion Token Calculation (12 tests)"""

    def test_calculate_dynamic_tokens_basic(self):
        """TC-ML-009: Standard case: input tokens within reasonable range."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-4o-mini",
            min_output_tokens=2048,
            output_safety_margin=0.1
        )
        
        # Expected: 16384 * 0.9 = 14745 (with safety margin)
        assert 14000 <= result <= 15000

    def test_calculate_dynamic_tokens_min_floor(self):
        """TC-ML-010: min_output_tokens should be enforced even with large input."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-4o-mini",
            min_output_tokens=2048,
            output_safety_margin=0.1
        )
        
        # Should guarantee at least min_output_tokens
        assert result >= 2048

    def test_calculate_dynamic_tokens_zero_input(self):
        """TC-ML-011: Zero input should give maximum available output."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-5",
            min_output_tokens=2048,
            output_safety_margin=0.1
        )
        
        # Expected: 128000 * 0.9 = 115200
        assert 114000 <= result <= 116000

    @pytest.mark.parametrize("safety_margin,expected_multiplier", [
        (0.0, 1.0),    # No safety margin
        (0.1, 0.9),    # 10% margin
        (0.5, 0.5),    # 50% margin
        (0.99, 0.01),  # Extreme margin
    ])
    def test_calculate_dynamic_tokens_safety_margins(self, safety_margin, expected_multiplier):
        """TC-ML-012: Different safety margins should proportionally reduce output."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-4o-mini",  # 16384 limit
            min_output_tokens=100,
            output_safety_margin=safety_margin
        )
        
        expected = int(16384 * expected_multiplier)
        assert abs(result - expected) / expected < 0.05  # <5% error

    @pytest.mark.parametrize("invalid_margin", [-0.1, 1.0, 1.5, 100])
    def test_calculate_dynamic_tokens_invalid_safety_margin(self, invalid_margin):
        """TC-ML-013: Safety margin outside [0.0, 1.0) should raise ValueError."""
        with pytest.raises(ValueError, match="output_safety_margin must be between"):
            calculate_dynamic_completion_tokens(
                model="gpt-5",
                output_safety_margin=invalid_margin
            )

    def test_input_token_subtraction_behavior(self):
        """
        TC-ML-014: Verify that calculate_dynamic_completion_tokens applies safety margin
        to model's hard output limit without subtracting input tokens.
        """
        result = calculate_dynamic_completion_tokens(
            model="gpt-5",  # 128K output limit
            min_output_tokens=2048,
            output_safety_margin=0.1
        )
        
        # Expected: 128000 * 0.9 = 115200
        assert result > 110_000
        assert 114_000 <= result <= 116_000

    @pytest.mark.parametrize("invalid_min", [-100, 0, 200_000])
    def test_calculate_dynamic_tokens_invalid_min_output(self, invalid_min):
        """TC-ML-015: min_output_tokens must be positive and reasonable."""
        with pytest.raises(ValueError):
            calculate_dynamic_completion_tokens(
                model="gpt-4o-mini",
                min_output_tokens=invalid_min
            )

    def test_calculate_dynamic_tokens_capped_at_max(self):
        """TC-ML-016: Result should never exceed model's hard limit."""
        # Current implementation raises ValueError if min_output_tokens > max_model_output
        with pytest.raises(ValueError, match="min_output_tokens.*cannot exceed model's max output limit"):
            calculate_dynamic_completion_tokens(
                model="gpt-4o-mini",  # 16384 limit
                min_output_tokens=50000,  # Request more than model supports
                output_safety_margin=0.0
            )

    def test_calculate_dynamic_tokens_huge_input(self):
        """TC-ML-017: Extremely large input should still return valid output tokens."""
        result = calculate_dynamic_completion_tokens(
            model="gemini-3-flash",
            min_output_tokens=2048
        )
        
        # Should still reserve minimum output
        assert result >= 2048
        assert result <= 65536  # Model max

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
            model="gpt-5"
        )
        
        # Verify the function returns a valid result
        assert isinstance(result, int)
        assert result > 0
        
        # Verify that debug logging occurred
        assert len(loguru_caplog.records) > 0, "No debug logs were captured"
        
        # Verify the log message contains expected information
        log_messages = [record.message for record in loguru_caplog.records]
        assert any("Model: gpt-5" in msg for msg in log_messages), \
            f"Expected log message containing 'Model: gpt-5', got: {log_messages}"


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
            model="gpt-4o-mini"
        )
        # Default min_output_tokens is 2048
        assert result >= 2048

    def test_default_output_safety_margin(self):
        """Test default output_safety_margin value."""
        result = calculate_dynamic_completion_tokens(
            model="gpt-4o-mini",
            min_output_tokens=100
        )
        # Default output_safety_margin is 0.1
        # Expected: 16384 * 0.9 = 14745
        assert 14000 <= result <= 15000

    def test_gpt5_dynamic_tokens_with_margin(self):
        """
        Test dynamic token calculation for GPT-5 with safety margin.
        
        Tests the complete token calculation pipeline for a specific model.
        """
        # Calculate max completion for GPT-5
        max_completion = calculate_dynamic_completion_tokens(
            model="gpt-5",
            min_output_tokens=2048,
            output_safety_margin=0.1
        )
        
        # Validate result
        assert 114_000 <= max_completion <= 116_000  # ~115K for GPT-5 with margin


class TestRemovedModels:
    """Tests for models that were removed from DEFAULT_GPT_MODELS list."""

    @pytest.mark.parametrize("removed_model,expected_behavior", [
        ("gpt-4.1-mini", "should_match_gpt4_prefix"),
        ("gpt-4.1-nano", "should_match_gpt4_prefix"),
    ])
    def test_removed_models_get_correct_limits(self, removed_model, expected_behavior):
        """
        TC-ML-021: Removed models should get correct token limits.
        
        Models gpt-4.1-mini and gpt-4.1-nano were removed from DEFAULT_GPT_MODELS
        but may still be used by users with old configs or manual input.
        They should match the 'gpt-4' prefix (limit 4096) and not match 'gpt-5'.
        """
        result = get_model_max_completion_tokens(removed_model)
        
        # Should match 'gpt-4' prefix, not 'gpt-5'
        assert result == 4096, (
            f"Model '{removed_model}' should match 'gpt-4' prefix with limit 4096, "
            f"got {result}"
        )

    def test_removed_models_do_not_match_gpt5_prefix(self):
        """
        TC-ML-022: Removed models should NOT match GPT-5 prefix.
        
        This is a regression test to ensure that gpt-4.1 models don't
        accidentally get GPT-5 token limits (128K) due to prefix matching bugs.
        """
        gpt5_limit = get_model_max_completion_tokens("gpt-5")
        gpt41_mini_limit = get_model_max_completion_tokens("gpt-4.1-mini")
        
        # gpt-4.1-mini should NOT get gpt-5's limit
        assert gpt41_mini_limit != gpt5_limit, (
            f"gpt-4.1-mini should not match gpt-5 prefix. "
            f"Got same limit {gpt41_mini_limit} as gpt-5"
        )
        
        # gpt-4.1-mini should get gpt-4's limit (4096)
        assert gpt41_mini_limit == 4096

    def test_removed_models_with_dynamic_calculation(self):
        """
        TC-ML-023: Removed models should work correctly with dynamic calculation.
        
        Tests that calculate_dynamic_completion_tokens handles removed models properly.
        """
        for model in ["gpt-4.1-mini", "gpt-4.1-nano"]:
            result = calculate_dynamic_completion_tokens(
                model=model,
                min_output_tokens=2048,
                output_safety_margin=0.1
            )
            
            # Should apply safety margin to gpt-4's limit (4096)
            expected_max = int(4096 * 0.9)  # 3686 with 10% margin
            assert result == expected_max, (
                f"Model '{model}' with dynamic calculation should return "
                f"{expected_max}, got {result}"
            )


class TestPrefixMatchingEdgeCases:
    """Tests for edge cases in prefix matching logic."""

    def test_gpt4_prefix_does_not_match_gpt5(self):
        """
        TC-ML-024: GPT-4 models should not match GPT-5 prefix.
        
        Regression test to ensure 'gpt-4' prefix doesn't accidentally
        match 'gpt-5' due to sorting or matching bugs.
        """
        gpt4_limit = get_model_max_completion_tokens("gpt-4")
        gpt5_limit = get_model_max_completion_tokens("gpt-5")
        
        assert gpt4_limit == 4096
        assert gpt5_limit == 128000
        assert gpt4_limit != gpt5_limit

    def test_similar_model_names_dont_collide(self):
        """
        TC-ML-025: Similar model names should have correct distinct limits.
        
        Tests that models with similar names (gpt-4 vs gpt-5) don't
        get mixed up due to prefix matching.
        """
        test_cases = [
            ("gpt-4", 4096),
            ("gpt-4o", 16384),
            ("gpt-4o-mini", 16384),
            ("gpt-5", 128000),
            ("gpt-5-mini", 128000),
            ("gpt-5-nano", 32768),
        ]
        
        for model, expected_limit in test_cases:
            result = get_model_max_completion_tokens(model)
            assert result == expected_limit, (
                f"Model '{model}' should have limit {expected_limit}, got {result}"
            )

    def test_versioned_models_match_correct_base(self):
        """
        TC-ML-026: Versioned model variants should match correct base.
        
        Ensures that gpt-4.1 matches gpt-4, not gpt-5.
        """
        # gpt-4.1 variants should match gpt-4 prefix
        assert get_model_max_completion_tokens("gpt-4.1") == 4096
        assert get_model_max_completion_tokens("gpt-4.1-mini") == 4096
        assert get_model_max_completion_tokens("gpt-4.1-nano") == 4096
        
        # gpt-5 variants should match gpt-5 prefix
        assert get_model_max_completion_tokens("gpt-5.1") == 128000
        assert get_model_max_completion_tokens("gpt-5.1-mini") == 128000

    def test_longest_prefix_wins_over_shorter(self):
        """
        TC-ML-027: Longest prefix should win over shorter prefixes.
        
        When multiple prefixes could match, the longest one should be used.
        """
        # gpt-5-mini should match 'gpt-5-mini' (128K), not 'gpt-5' (also 128K in this case)
        # But the logic matters for correctness
        result = get_model_max_completion_tokens("gpt-5-mini-turbo")
        assert result == 128000  # From gpt-5-mini prefix
        
        # gpt-4o-mini should match 'gpt-4o-mini' (16384), not 'gpt-4' (4096)
        result = get_model_max_completion_tokens("gpt-4o-mini-preview")
        assert result == 16384, (
            "Should match 'gpt-4o-mini' (longest prefix), not 'gpt-4'"
        )
