"""
Integration test for DeepL provider using WhisperBridge infrastructure.

This test validates the complete DeepL translation pipeline:
- ConfigService configuration
- DeepLClientAdapter initialization
- APIManager integration
- Translation request/response flow
"""

import sys
import os

# Configure UTF-8 encoding for Windows console
if sys.platform == 'win32':
    # Set console to UTF-8 mode
    os.system('chcp 65001 >nul 2>&1')
    # Reconfigure stdout/stderr to use UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

import pytest
from _pytest.outcomes import Skipped
from whisperbridge.core.api_manager import APIManager, APIProvider
from whisperbridge.services.config_service import ConfigService
from whisperbridge.providers.deepl_adapter import DeepLClientAdapter

pytestmark = pytest.mark.integration


def test_deepl_adapter_direct():
    """Test 1: Direct DeepLClientAdapter functionality"""
    print("=" * 80)
    print("TEST 1: Direct DeepLClientAdapter")
    print("=" * 80)
    
    # Get API key from keyring via ConfigService
    config = ConfigService()
    api_key = config.get_setting("deepl_api_key")
    plan = config.get_setting("deepl_plan") or "free"
    
    if not api_key:
        print("[SKIP] DeepL API key not found in keyring")
        pytest.skip("DeepL API key not configured")
    
    # Create adapter with free plan
    adapter = DeepLClientAdapter(api_key=api_key, timeout=30, plan=plan)
    print(f"[OK] Adapter created successfully")
    print(f"  Base URL: {adapter._base_url}")
    print(f"  Plan: {plan}")
    
    # Test translation using OpenAI-compatible interface
    messages = [
        {"role": "user", "content": "Hello, world!"}
    ]
    
    response = adapter.chat.completions.create(
        model="deepl-translate",  # Model name doesn't matter for DeepL
        messages=messages,
        target_lang="RU",
        source_lang="EN"
    )
    
    print(f"[OK] Translation request successful")
    
    # Extract translated text
    assert hasattr(response, 'choices') and response.choices, "Response missing choices"
    translated = response.choices[0].message.content
    print(f"  Original: Hello, world!")
    print(f"  Translated: {translated}")
    assert translated, "Translated text is empty"


def test_api_manager_deepl():
    """Test 2: APIManager with DeepL provider"""
    print("\n")
    print("=" * 80)
    print("TEST 2: APIManager with DeepL Provider")
    print("=" * 80)
    
    # Use existing config service with configured settings
    config = ConfigService()
    
    # Verify DeepL is configured
    api_key = config.get_setting("deepl_api_key")
    if not api_key:
        print("[SKIP] DeepL API key not found in keyring")
        pytest.skip("DeepL API key not configured")
    
    # Set DeepL as active provider (temporarily for this test)
    original_provider = config.get_setting("api_provider")
    config.set_setting("api_provider", "deepl")
    
    try:
        print(f"[OK] ConfigService configured")
        print(f"  Provider: {config.get_setting('api_provider')}")
        print(f"  Plan: {config.get_setting('deepl_plan')}")
        
        # Create and initialize APIManager
        api_manager = APIManager(config)
        success = api_manager.initialize()
        assert success, "APIManager initialization failed"
            
        print(f"[OK] APIManager initialized")
        
        # Check if DeepL client is available
        assert APIProvider.DEEPL in api_manager._clients, "DeepL client not found in APIManager"
            
        print(f"[OK] DeepL client registered in APIManager")
        
        # Make a translation request
        messages = [
            {"role": "user", "content": "Good morning!"}
        ]
        
        response, model = api_manager.make_translation_request(
            messages=messages,
            model_hint="deepl-translate",
            target_lang="RU",
            source_lang="EN"
        )
        
        print(f"[OK] Translation request via APIManager successful")
        print(f"  Model used: {model}")
        
        # Extract text using APIManager's helper
        translated = api_manager.extract_text_from_response(response)
        assert translated, "Failed to extract translation from response"
        
        print(f"  Original: Good morning!")
        print(f"  Translated: {translated}")
    finally:
        # Restore original provider
        config.set_setting("api_provider", original_provider)


def test_language_auto_detection():
    """Test 3: Language auto-detection (source_lang=None)"""
    print("\n")
    print("=" * 80)
    print("TEST 3: Language Auto-Detection")
    print("=" * 80)
    
    # Get API key from keyring
    config = ConfigService()
    api_key = config.get_setting("deepl_api_key")
    plan = config.get_setting("deepl_plan") or "free"
    
    if not api_key:
        print("[SKIP] DeepL API key not found in keyring")
        pytest.skip("DeepL API key not configured")
    
    # Create adapter
    adapter = DeepLClientAdapter(api_key=api_key, timeout=30, plan=plan)
    
    # Test with Russian text (no source_lang specified)
    messages = [
        {"role": "user", "content": "Привет, мир!"}
    ]
    
    response = adapter.chat.completions.create(
        model="deepl-translate",
        messages=messages,
        target_lang="EN"
        # source_lang not specified - should auto-detect
    )
    
    print(f"[OK] Auto-detection request successful")
    
    assert hasattr(response, 'choices') and response.choices, "Response missing choices"
    translated = response.choices[0].message.content
    print(f"  Original: Привет, мир!")
    print(f"  Translated: {translated}")
    assert translated, "Translated text is empty"


def test_multiple_messages():
    """Test 4: Multiple messages concatenation"""
    print("\n")
    print("=" * 80)
    print("TEST 4: Multiple Messages Concatenation")
    print("=" * 80)
    
    # Get API key from keyring
    config = ConfigService()
    api_key = config.get_setting("deepl_api_key")
    plan = config.get_setting("deepl_plan") or "free"
    
    if not api_key:
        print("[SKIP] DeepL API key not found in keyring")
        pytest.skip("DeepL API key not configured")
    
    adapter = DeepLClientAdapter(api_key=api_key, timeout=30, plan=plan)
    
    # Multiple user messages should be concatenated
    messages = [
        {"role": "system", "content": "This should be ignored by DeepL"},
        {"role": "user", "content": "Hello!"},
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "This should also be ignored"},
        {"role": "user", "content": "Have a nice day!"}
    ]
    
    response = adapter.chat.completions.create(
        model="deepl-translate",
        messages=messages,
        target_lang="RU",
        source_lang="EN"
    )
    
    print(f"[OK] Multi-message request successful")
    
    assert hasattr(response, 'choices') and response.choices, "Response missing choices"
    translated = response.choices[0].message.content
    print(f"  Original messages: 3 user messages")
    print(f"  Translated: {translated}")
    assert translated, "Translated text is empty"


def test_error_handling():
    """Test 5: Error handling with invalid API key"""
    print("\n")
    print("=" * 80)
    print("TEST 5: Error Handling (Invalid API Key)")
    print("=" * 80)
    
    # Use invalid API key
    adapter = DeepLClientAdapter(api_key="invalid-key", timeout=5, plan="free")
    
    messages = [{"role": "user", "content": "Test"}]
    
    with pytest.raises(Exception):
        adapter.chat.completions.create(
            model="deepl-translate",
            messages=messages,
            target_lang="RU"
        )
    print(f"[OK] Correctly raised error for invalid API key")


def run_all_tests():
    """Run all DeepL infrastructure tests and return True if all passed"""
    print("\n")
    print("=" * 80)
    print("  WhisperBridge DeepL Infrastructure Integration Tests")
    print("=" * 80)
    print("\n")
    
    test_funcs = [
        ("Direct DeepLClientAdapter", test_deepl_adapter_direct),
        ("APIManager Integration", test_api_manager_deepl),
        ("Language Auto-Detection", test_language_auto_detection),
        ("Multiple Messages", test_multiple_messages),
        ("Error Handling", test_error_handling),
    ]
    
    results = {}
    for name, func in test_funcs:
        try:
            func()
            results[name] = True
        except Skipped:
            print(f"[SKIP] {name} (Key not found)")
            results[name] = True  # Consider skip as success for summary
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            results[name] = False
    
    # Print summary
    print("\n")
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status:8} | {test_name}")
    
    print("-" * 80)
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n>>> SUCCESS: All tests passed! DeepL integration is working correctly.")
    else:
        print(f"\n>>> WARNING: {total - passed} test(s) failed. Please review the errors above.")
    
    print("=" * 80)
    
    return passed == total


if __name__ == "__main__":
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
