# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- LLM-based OCR engine — adds an alternative OCR flow using OpenAI or Google Generative AI vision models alongside the existing EasyOCR engine.
  - Configurable via `ocr_engine` ("easyocr" or "llm"); default remains "easyocr".
  - Automatic fallback to EasyOCR when LLM OCR fails or returns empty results.
  - Image handling optimized for LLM vision: natural-image flow, long edge capped (~1280px), and JPEG encoding for upload.
  - Background execution: all OCR/LLM work runs in background QThread workers; network calls are off the UI thread and UI updates occur via signals/slots.
  - Retry/backoff policies reuse APIManager semantics for transient failures.
- New configuration settings:
  - `ocr_engine` (default: "easyocr")
  - `ocr_llm_prompt` (custom LLM OCR prompt)
  - `openai_vision_model` (default: gpt-4o-mini)
  - `google_vision_model` (default: gemini-2.5-flash)
- Settings UI improvements:
  - OCR engine selector and LLM OCR prompt field added to the settings dialog.
  - Provider-specific vision model fields with visibility toggles and API-key gating.
  - Interactive help hints (question-mark buttons) with explanatory tooltips — see [`src/whisperbridge/utils/help_texts.py`](src/whisperbridge/utils/help_texts.py:1).
- Testing:
  - Added tests in [`tests/test_ocr_llm.py`](tests/test_ocr_llm.py:1) covering fast-path, success, fallback-to-EasyOCR, and disabled scenarios.
- Documentation:
  - Project docs and README files updated to describe the LLM OCR option, configuration keys, UI surfaces, and performance/cost notes.

### Technical details
- Performance: long-edge image capping (~1280px), JPEG encoding (quality tuned for size/cost), zero temperature (deterministic outputs), token limits applied (~2048 completion tokens).
- Threading: long-running and network operations are performed in background QThreads; UI mutation happens only on the main thread via signals/slots.
- Image processing: LLM OCR uses natural-image preprocessing (no binarization/sharpening); EasyOCR pipeline remains unchanged.

### Changed
- Default OCR engine remains EasyOCR to preserve backward compatibility.
- OCR service extended to support dual-engine flow (LLM → EasyOCR fallback).
- APIManager extended with vision request methods for both OpenAI and Google providers.

## [0.1.0] - 2024-10-01

### Added
- Initial release of WhisperBridge
- Screen region capture and OCR using EasyOCR
- Translation via OpenAI GPT API
- Qt/PySide6 desktop interface with overlays
- Global hotkeys and system tray integration
- Basic settings and configuration management