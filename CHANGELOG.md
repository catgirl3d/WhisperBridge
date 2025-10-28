# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **LLM-based OCR Engine**: New OCR option using OpenAI or Google Generative AI vision models alongside existing EasyOCR
  - Configurable OCR engine selection via settings (`ocr_engine`: "easyocr" or "llm")
  - Automatic fallback to EasyOCR if LLM OCR fails or returns empty results
  - Image preprocessing optimized for LLM vision models (natural images, size capping, JPEG encoding)
  - Threading discipline maintained: all OCR/LLM work in background threads
  - Retry/backoff policies using existing APIManager semantics
- **New Configuration Settings**:
  - `ocr_engine`: Choose between "easyocr" (default) and "llm"
  - `ocr_llm_prompt`: Customizable prompt for LLM OCR
  - `openai_vision_model`: Vision model for OpenAI (default: gpt-4o-mini)
  - `google_vision_model`: Vision model for Google (default: gemini-2.5-flash)
- **Settings UI Enhancements**:
  - OCR Engine selector in settings dialog
  - LLM OCR Prompt configuration field
  - Provider-specific vision model fields with visibility toggles
  - Interactive help hints: Question mark (?) buttons next to all settings fields with tooltips and detailed explanations on click
- **Testing Coverage**: New test suite [`test_ocr_llm.py`](tests/test_ocr_llm.py) covering LLM OCR fast-path, success, fallback, and disabled scenarios
- **Documentation Updates**:  - Project documentation with new settings, UI surfaces, core flows, and performance notes
  - README files updated to mention LLM OCR option

### Technical Details
- **Performance Optimizations**: Image size capping (~1280px long edge), zero temperature for deterministic results, token limits (~2048 completion tokens)
- **Threading**: All network calls off UI thread using QThread workers and signals/slots
- **Image Processing**: Natural image handling without binarization/sharpening (LLM-specific vs EasyOCR preprocessing)

### Changed
- Default OCR engine remains EasyOCR for backward compatibility
- Enhanced OCR service with dual-engine support and fallback logic
- Updated API manager with vision request methods for both OpenAI and Google providers


## [0.1.0] - 2024-10-01

### Added
- Initial release of WhisperBridge
- Screen region capture and OCR using EasyOCR
- Translation via OpenAI GPT API
- Qt/PySide6 desktop interface with overlays
- Global hotkeys and system tray integration
- Basic settings and configuration management