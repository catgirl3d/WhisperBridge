"""
Unit tests for VK-encoding functionality in KeyboardUtils.

Tests the VK code resolution and mapping for hotkey handling.
"""

import pytest
from whisperbridge.utils.keyboard_utils import KeyboardUtils, WIN_VK_MAP, _VK_TO_NAME_MAP


class TestGetVksForHotkey:
    """Tests for get_vks_for_hotkey method."""

    def test_empty_hotkey_returns_empty_set(self):
        """Test that empty hotkey returns empty set."""
        assert KeyboardUtils.get_vks_for_hotkey("") == set()

    def test_none_hotkey_returns_empty_set(self):
        """Test that None hotkey returns empty set."""
        assert KeyboardUtils.get_vks_for_hotkey(None) == set()

    def test_single_key_returns_correct_vk(self):
        """Test that single key returns correct VK code."""
        # Test 'a' key
        result = KeyboardUtils.get_vks_for_hotkey("a")
        assert result == {WIN_VK_MAP["a"]}

        # Test '1' key
        result = KeyboardUtils.get_vks_for_hotkey("1")
        assert result == {WIN_VK_MAP["1"]}

    def test_modifier_only_returns_empty_set(self):
        """Test that modifier only returns empty set (requires main key)."""
        result = KeyboardUtils.get_vks_for_hotkey("ctrl")
        # normalize_hotkey() requires a main key, so modifier-only returns empty set
        assert result == set()

    def test_hotkey_with_modifiers_returns_all_vks(self):
        """Test that hotkey with modifiers returns all VK codes."""
        result = KeyboardUtils.get_vks_for_hotkey("ctrl+alt+j")
        expected = {WIN_VK_MAP["ctrl"], WIN_VK_MAP["alt"], WIN_VK_MAP["j"]}
        assert result == expected

    def test_hotkey_with_multiple_modifiers(self):
        """Test hotkey with multiple modifiers."""
        result = KeyboardUtils.get_vks_for_hotkey("ctrl+shift+a")
        expected = {WIN_VK_MAP["ctrl"], WIN_VK_MAP["shift"], WIN_VK_MAP["a"]}
        assert result == expected

    def test_function_key_returns_correct_vk(self):
        """Test that function keys return correct VK codes."""
        result = KeyboardUtils.get_vks_for_hotkey("f1")
        assert result == {WIN_VK_MAP["f1"]}

        result = KeyboardUtils.get_vks_for_hotkey("f12")
        assert result == {WIN_VK_MAP["f12"]}

    def test_special_key_returns_correct_vk(self):
        """Test that special keys return correct VK codes."""
        result = KeyboardUtils.get_vks_for_hotkey("enter")
        assert result == {WIN_VK_MAP["enter"]}

        result = KeyboardUtils.get_vks_for_hotkey("space")
        assert result == {WIN_VK_MAP["space"]}

        result = KeyboardUtils.get_vks_for_hotkey("esc")
        assert result == {WIN_VK_MAP["esc"]}

    def test_navigation_keys_return_correct_vk(self):
        """Test that navigation keys return correct VK codes."""
        result = KeyboardUtils.get_vks_for_hotkey("up")
        assert result == {WIN_VK_MAP["up"]}

        result = KeyboardUtils.get_vks_for_hotkey("down")
        assert result == {WIN_VK_MAP["down"]}

        result = KeyboardUtils.get_vks_for_hotkey("left")
        assert result == {WIN_VK_MAP["left"]}

        result = KeyboardUtils.get_vks_for_hotkey("right")
        assert result == {WIN_VK_MAP["right"]}

        result = KeyboardUtils.get_vks_for_hotkey("home")
        assert result == {WIN_VK_MAP["home"]}

        result = KeyboardUtils.get_vks_for_hotkey("end")
        assert result == {WIN_VK_MAP["end"]}

        result = KeyboardUtils.get_vks_for_hotkey("pageup")
        assert result == {WIN_VK_MAP["pageup"]}

        result = KeyboardUtils.get_vks_for_hotkey("pagedown")
        assert result == {WIN_VK_MAP["pagedown"]}

    def test_win_modifier_returns_empty_set(self):
        """Test that win modifier only returns empty set (requires main key)."""
        result = KeyboardUtils.get_vks_for_hotkey("win")
        # normalize_hotkey() requires a main key, so modifier-only returns empty set
        assert result == set()

    def test_hotkey_order_does_not_matter(self):
        """Test that hotkey key order doesn't affect result."""
        result1 = KeyboardUtils.get_vks_for_hotkey("ctrl+alt+j")
        result2 = KeyboardUtils.get_vks_for_hotkey("alt+ctrl+j")
        result3 = KeyboardUtils.get_vks_for_hotkey("j+ctrl+alt")
        assert result1 == result2 == result3

    def test_case_insensitive(self):
        """Test that hotkey is case-insensitive."""
        result1 = KeyboardUtils.get_vks_for_hotkey("ctrl+A")
        result2 = KeyboardUtils.get_vks_for_hotkey("CTRL+a")
        result3 = KeyboardUtils.get_vks_for_hotkey("Ctrl+a")
        assert result1 == result2 == result3

    def test_unknown_key_returns_empty_set(self):
        """Test that unknown key in combination returns empty set."""
        result = KeyboardUtils.get_vks_for_hotkey("ctrl+unknown")
        assert result == set()

    def test_non_windows_platform_returns_empty_set(self, monkeypatch):
        """Test that non-Windows platform returns empty set."""
        # Mock get_platform to return linux
        monkeypatch.setattr(KeyboardUtils, "get_platform", lambda: "linux")
        result = KeyboardUtils.get_vks_for_hotkey("ctrl+a")
        assert result == set()


class TestGetNameFromVk:
    """Tests for get_name_from_vk method."""

    def test_valid_vk_returns_name(self):
        """Test that valid VK code returns correct name."""
        assert KeyboardUtils.get_name_from_vk(WIN_VK_MAP["a"]) == "a"
        assert KeyboardUtils.get_name_from_vk(WIN_VK_MAP["ctrl"]) == "ctrl"
        assert KeyboardUtils.get_name_from_vk(WIN_VK_MAP["alt"]) == "alt"

    def test_invalid_vk_returns_none(self):
        """Test that invalid VK code returns None."""
        assert KeyboardUtils.get_name_from_vk(0) is None
        assert KeyboardUtils.get_name_from_vk(9999) is None
        assert KeyboardUtils.get_name_from_vk(-1) is None

    def test_all_letters_mapped(self):
        """Test that all letters a-z are mapped."""
        for letter in "abcdefghijklmnopqrstuvwxyz":
            vk = WIN_VK_MAP[letter]
            assert KeyboardUtils.get_name_from_vk(vk) == letter

    def test_all_numbers_mapped(self):
        """Test that all numbers 0-9 are mapped."""
        for number in "0123456789":
            vk = WIN_VK_MAP[number]
            assert KeyboardUtils.get_name_from_vk(vk) == number

    def test_all_function_keys_mapped(self):
        """Test that all function keys f1-f12 are mapped."""
        for i in range(1, 13):
            key = f"f{i}"
            vk = WIN_VK_MAP[key]
            assert KeyboardUtils.get_name_from_vk(vk) == key

    def test_all_modifiers_mapped(self):
        """Test that all modifiers are mapped."""
        for modifier in ["ctrl", "alt", "shift", "win"]:
            vk = WIN_VK_MAP[modifier]
            assert KeyboardUtils.get_name_from_vk(vk) == modifier

    def test_all_special_keys_mapped(self):
        """Test that all special keys are mapped."""
        special_keys = ["space", "enter", "esc", "tab", "backspace", "delete",
                       "up", "down", "left", "right", "home", "end",
                       "pageup", "pagedown", "insert"]
        for key in special_keys:
            vk = WIN_VK_MAP[key]
            assert KeyboardUtils.get_name_from_vk(vk) == key


class TestVkMapConsistency:
    """Tests for VK map consistency and bidirectional mapping."""

    def test_vk_map_is_bidirectional(self):
        """Test that VK map is consistent in both directions."""
        for name, vk in WIN_VK_MAP.items():
            assert _VK_TO_NAME_MAP[vk] == name, f"VK {vk} for '{name}' not in reverse map"

    def test_vk_map_has_no_duplicates(self):
        """Test that VK map has no duplicate VK codes."""
        vk_values = list(WIN_VK_MAP.values())
        assert len(vk_values) == len(set(vk_values)), "VK map has duplicate values"

    def test_reverse_map_has_no_duplicates(self):
        """Test that reverse VK map has no duplicate names."""
        name_values = list(_VK_TO_NAME_MAP.values())
        assert len(name_values) == len(set(name_values)), "Reverse VK map has duplicate values"
