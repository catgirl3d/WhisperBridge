"""
Minimal tests for worker classes.
Run with: python -m pytest test_workers.py
"""

import pytest
from unittest.mock import Mock

from whisperbridge.ui_qt.workers import ApiTestWorker, ModelListWorker
from whisperbridge.core.provider_catalog import APIProvider

# If run directly, execute pytest with very verbose output and no coverage
if __name__ == "__main__":
    pytest.main([__file__, "-vv", "--no-cov"])

class TestWorkers:
    """Test worker signal emissions."""

    def test_model_list_worker_success(self, qapp, mocker):
        """ModelListWorker emits the provider, models, and source from APIManager."""
        mock_get_api = mocker.patch("whisperbridge.ui_qt.workers.get_api_manager")
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = (["gpt-5.4-mini"], "cache")
        mock_get_api.return_value = mock_api

        worker = ModelListWorker("openai", generation=3, model_to_select="gpt-5.4-mini")
        results = []
        worker.finished.connect(lambda *args: results.append(list(args)))

        worker.run()

        assert results == [["openai", ["gpt-5.4-mini"], "cache", 3, "gpt-5.4-mini"]]
        mock_api.get_available_models_sync.assert_called_once_with(
            provider=APIProvider.OPENAI,
            temp_api_key=None,
        )

    def test_model_list_worker_error_emits_error_source(self, qapp, mocker):
        """ModelListWorker converts a failed fetch into an empty error result."""
        mock_get_api = mocker.patch("whisperbridge.ui_qt.workers.get_api_manager")
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.side_effect = RuntimeError("API down")
        mock_get_api.return_value = mock_api

        worker = ModelListWorker("google", generation=4)
        results = []
        worker.finished.connect(lambda *args: results.append(list(args)))

        worker.run()

        assert results == [["google", [], "error", 4, None]]

    def test_api_test_worker_success(self, qapp, mocker):
        """Test ApiTestWorker emits finished on success."""
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = (['gpt-5.4-mini'], 'mock')
        mock_get_api.return_value = mock_api

        worker = ApiTestWorker('openai', 'sk-test')
        results = []
        worker.finished.connect(lambda *args: results.append(list(args)))
        worker.run()

        assert results == [[True, '', ['gpt-5.4-mini'], 'mock']]
        mock_api.get_available_models_sync.assert_called_once_with(
            provider=APIProvider.OPENAI, temp_api_key='sk-test'
        )
        mock_api.initialize.assert_not_called()

    def test_api_test_worker_error(self, qapp, mocker):
        """Test ApiTestWorker reports failure through its terminal signal."""
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = ([], 'error')
        mock_get_api.return_value = mock_api

        worker = ApiTestWorker('openai', 'sk-test')
        results = []
        worker.finished.connect(lambda *args: results.append(list(args)))
        worker.run()

        assert results == [[False, 'API error or invalid key', [], '']]
        with pytest.raises(AttributeError):
            worker.error
        mock_api.get_available_models_sync.assert_called_once_with(
            provider=APIProvider.OPENAI, temp_api_key='sk-test'
        )
        mock_api.initialize.assert_not_called()

    def test_translation_worker_success(self, qapp, mocker):
        """Test TranslationWorker translates text and emits finished signal."""
        from whisperbridge.ui_qt.workers import TranslationWorker
        from whisperbridge.utils.translation_utils import TranslationResponse

        mock_get_service = mocker.patch('whisperbridge.services.translation_service.get_translation_service')
        mock_service = Mock()
        mock_service.translate_text.return_value = TranslationResponse(
            success=True,
            translated_text="Привет мир",
        )
        mock_get_service.return_value = mock_service

        worker = TranslationWorker("Hello world", "en", "ru")
        results = []
        worker.finished.connect(lambda *args: results.append(list(args)))
        worker.run()

        assert results == [[True, "Привет мир"]]
        mock_service.translate_text.assert_called_once_with(
            "Hello world",
            ui_source_lang="en",
            ui_target_lang="ru",
        )

    def test_style_worker_success(self, qapp, mocker):
        """Test StyleWorker rewrites text and emits finished signal."""
        from whisperbridge.ui_qt.workers import StyleWorker
        from whisperbridge.utils.translation_utils import TranslationResponse

        mock_get_service = mocker.patch('whisperbridge.services.translation_service.get_translation_service')
        mock_service = Mock()
        mock_service.style_text.return_value = TranslationResponse(
            success=True,
            translated_text="Formal Hello",
        )
        mock_get_service.return_value = mock_service

        worker = StyleWorker("Hello", "Formal")
        results = []
        worker.finished.connect(lambda *args: results.append(list(args)))
        worker.run()

        assert results == [[True, "Formal Hello"]]
        mock_service.style_text.assert_called_once_with(
            "Hello",
            style_name="Formal",
        )
