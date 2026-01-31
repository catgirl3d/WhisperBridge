"""Test script for enhanced language detection."""

from whisperbridge.utils.language_utils import (
    detect_language,
    detect_language_with_confidence,
    normalize_homoglyphs,
    detect_mixed_scripts
)

def run_test_case(description, text, expected_lang=None, expected_mixed=None):
    """Test a single case and print results."""
    print(f"\n{'='*60}")
    print(f"Test: {description}")
    print(f"Text: '{text}'")
    print(f"{'='*60}")
    
    # Test new function with confidence
    result = detect_language_with_confidence(text)
    print(f"✓ Detected: {result.language} (confidence: {result.confidence:.2f})")
    print(f"✓ Mixed scripts: {result.mixed_scripts}")
    
    # Test backward compatible function
    old_result = detect_language(text)
    print(f"✓ Old API result: {old_result}")
    
    # Check expectations
    if expected_lang and result.language != expected_lang:
        print(f"❌ FAIL: Expected {expected_lang}, got {result.language}")
    elif expected_lang:
        print(f"✅ PASS: Language matches expected")
    
    if expected_mixed is not None and result.mixed_scripts != expected_mixed:
        print(f"❌ FAIL: Expected mixed={expected_mixed}, got {result.mixed_scripts}")
    elif expected_mixed is not None:
        print(f"✅ PASS: Mixed scripts detection correct")
    
    return result

def main():
    """Run all test cases."""
    print("Testing Enhanced Language Detection")
    print("="*60)
    
    # Test 1: The original problem - homoglyph false positive
    run_test_case(
        "Homoglyph Problem (OCR error: 'а' instead of 'a')",
        "Im currently investigating а users question in Russian",
        expected_lang="en",
        expected_mixed=True
    )
    
    # Test 2: Pure English
    run_test_case(
        "Pure English",
        "I am currently investigating a users question",
        expected_lang="en",
        expected_mixed=False
    )
    
    # Test 3: Pure Russian
    run_test_case(
        "Pure Russian",
        "Я сейчас исследую вопрос пользователя",
        expected_lang="ru",
        expected_mixed=False
    )
    
    # Test 4: Pure Ukrainian
    run_test_case(
        "Pure Ukrainian",
        "Я зараз досліджую питання користувача",
        expected_lang="ua",
        expected_mixed=False
    )
    
    # Test 5: Ukrainian with specific characters
    run_test_case(
        "Ukrainian with specific chars (і, ї, є, ґ)",
        "Це дуже гарний програмний застосунок для перекладу",
        expected_lang="ua",
        expected_mixed=False
    )
    
    # Test 6: Short text with homoglyphs
    run_test_case(
        "Short text with single homoglyph",
        "Hello а world",
        expected_lang="en",
        expected_mixed=True
    )
    
    # Test 7: Test normalization function directly
    print(f"\n{'='*60}")
    print("Testing homoglyph normalization")
    print(f"{'='*60}")
    
    test_texts = [
        "Im currently investigating а users question",
        "Hello а world с test",
        "Привет мир"
    ]
    
    for text in test_texts:
        normalized = normalize_homoglyphs(text, aggressive=False)
        print(f"\nOriginal:   '{text}'")
        print(f"Normalized: '{normalized}'")
        print(f"Mixed scripts: {detect_mixed_scripts(text)}")
    
    # Test 8: Low confidence threshold test
    run_test_case(
        "Very short ambiguous text",
        "а",
        expected_lang=None  # Should return None due to low confidence
    )
    
    # Test 9: Mixed languages (real mixed, not homoglyphs)
    run_test_case(
        "Intentionally mixed English and Russian",
        "Hello мир and привет world",
        expected_mixed=True
    )
    
    print(f"\n{'='*60}")
    print("All tests completed!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()