from whisperbridge.core.config import BUILD_OCR_ENABLED, Settings


def test_build_ocr_flag_is_boolean_gate():
    assert isinstance(BUILD_OCR_ENABLED, bool)


def test_settings_load_and_expose_runtime_toggle():
    settings = Settings()
    assert isinstance(settings.ocr_enabled, bool)


def test_ocr_enabled_reads_environment_override(monkeypatch):
    monkeypatch.setenv("OCR_ENABLED", "0")
    assert Settings().ocr_enabled is False

    monkeypatch.setenv("OCR_ENABLED", "1")
    assert Settings().ocr_enabled is True
