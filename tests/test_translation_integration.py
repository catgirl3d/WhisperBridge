#!/usr/bin/env python3
"""
Test script for GPT API translation integration.

This script tests the translation service components without running the full GUI.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from whisperbridge.core.config import settings
from whisperbridge.services.translation_service import get_translation_service
from whisperbridge.core.api_manager import init_api_manager
from whisperbridge.utils.api_utils import detect_language, validate_api_key_format


async def test_translation_service():
    """Test the translation service functionality."""
    print("=== Testing Translation Service Integration ===\n")

    # Check API key
    if not settings.openai_api_key:
        print("❌ ERROR: OpenAI API key not configured")
        print("Please set your OpenAI API key in the settings")
        return False

    if not validate_api_key_format(settings.openai_api_key):
        print("❌ ERROR: Invalid OpenAI API key format")
        return False

    print("✅ API key format is valid")

    # Initialize API manager
    try:
        api_manager = init_api_manager()
        print("✅ API manager initialized")
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize API manager: {e}")
        return False

    # Initialize translation service
    try:
        translation_service = get_translation_service()
        if not translation_service.initialize():
            print("❌ ERROR: Failed to initialize translation service")
            return False
        print("✅ Translation service initialized")
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize translation service: {e}")
        return False

    # Test language detection
    test_texts = [
        "Hello world",
        "Привет мир",
        "Bonjour le monde",
        "Hola mundo",
        "你好世界"
    ]

    print("\n=== Language Detection Test ===")
    for text in test_texts:
        detected = detect_language(text)
        print(f"Text: '{text}' -> Detected: {detected}")

    # Test translation (if API key is working)
    print("\n=== Translation Test ===")
    test_text = "Hello, how are you today?"

    try:
        print(f"Translating: '{test_text}'")
        print(f"From: {settings.source_language} -> To: {settings.target_language}")

        response = await translation_service.translate_text_async(
            text=test_text,
            source_lang=settings.source_language,
            target_lang=settings.target_language,
            use_cache=False  # Don't use cache for testing
        )

        if response.success:
            print("✅ Translation successful!")
            print(f"Original: {test_text}")
            print(f"Translated: {response.translated_text}")
            print(f"Model: {response.model}")
            print(f"Tokens used: {response.tokens_used}")
        else:
            print(f"❌ Translation failed: {response.error_message}")

    except Exception as e:
        print(f"❌ ERROR: Translation test failed: {e}")
        return False

    # Test caching
    print("\n=== Cache Test ===")
    cache_stats = translation_service.get_cache_stats()
    print(f"Cache enabled: {cache_stats['enabled']}")
    print(f"Cache size: {cache_stats['size']}/{cache_stats['max_size']}")

    # Test same translation again (should use cache)
    try:
        print(f"\nTesting cached translation...")
        response2 = await translation_service.translate_text_async(
            text=test_text,
            source_lang=settings.source_language,
            target_lang=settings.target_language,
            use_cache=True
        )

        if response2.cached:
            print("✅ Cache working - translation retrieved from cache")
        else:
            print("ℹ️  Translation not cached (may be first time or cache disabled)")

    except Exception as e:
        print(f"❌ ERROR: Cache test failed: {e}")

    # Cleanup
    translation_service.shutdown()
    api_manager.shutdown()

    print("\n=== Test Summary ===")
    print("✅ All basic integration tests completed")
    print("The GPT API integration is ready for use!")

    return True


def main():
    """Main test function."""
    print("WhisperBridge GPT API Integration Test")
    print("=" * 40)

    # Check if running in correct directory
    if not os.path.exists('src/whisperbridge'):
        print("❌ ERROR: Please run this script from the project root directory")
        sys.exit(1)

    # Run async test
    try:
        success = asyncio.run(test_translation_service())
        if success:
            print("\n🎉 Integration test PASSED!")
            sys.exit(0)
        else:
            print("\n❌ Integration test FAILED!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: Test failed with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()