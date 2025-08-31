#!/usr/bin/env python3
"""
Full workflow integration test for WhisperBridge.

This test uses a robust patching strategy by starting and stopping mocks within
the setUp method, which is the standard and most reliable way to handle
complex test setups in unittest.
"""

import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from PIL import Image

from whisperbridge.ui.app import WhisperBridgeApp
from whisperbridge.services.screen_capture_service import CaptureResult
from whisperbridge.services.ocr_service import OCRRequest

class TestFullWorkflow(unittest.IsolatedAsyncioTestCase):
    """Test the full application workflow with a fully mocked app instance."""

    def setUp(self):
        """Set up the test case by creating a fully mocked app instance."""
        
        # This is the standard, robust way to handle multiple patches in unittest.
        # We start each patcher manually and register its `stop` method for cleanup.
        patchers = {
            'ctk': patch('customtkinter.CTk', new_callable=MagicMock),
            'init_translation': patch('whisperbridge.ui.app.WhisperBridgeApp._initialize_translation_service'),
            'init_ocr': patch('whisperbridge.ui.app.WhisperBridgeApp._initialize_ocr_service'),
            'init_overlay': patch('whisperbridge.ui.app.WhisperBridgeApp._initialize_overlay_service'),
            'create_keyboard': patch('whisperbridge.ui.app.WhisperBridgeApp._create_keyboard_services'),
            'create_tray': patch('whisperbridge.ui.app.WhisperBridgeApp._create_tray_service'),
        }

        # Start all patchers and add their `stop` methods to cleanup
        for name, patcher in patchers.items():
            self.addCleanup(patcher.stop)
            patcher.start()

        # Instantiate the app. Its initialization methods are now patched to do nothing.
        self.app = WhisperBridgeApp()

        # Manually inject our mocks for the services.
        self.app.tray_service = MagicMock()
        self.app.hotkey_service = MagicMock()
        self.app.overlay_service = MagicMock()
        
        # Since we've bypassed the real initialization, set the running flag manually.
        self.app.is_running = True
        
        # Directly patch the method on the instance for this test
        self.app.update_tray_status = MagicMock()

    @patch('whisperbridge.ui.app.asyncio.create_task')
    @patch('whisperbridge.services.screen_capture_service.capture_area_interactive')
    async def test_translation_workflow_integration(self, mock_capture, mock_create_task):
        """
        Verify the main workflow is connected from hotkey to async processing.
        """
        # --- 1. Mocks Setup ---
        
        # Mock the app's internal async method to isolate the workflow connection.
        self.app._process_ocr_async = AsyncMock()
        
        # Capture the coroutine that will be scheduled.
        created_coroutines = []
        def side_effect(coro):
            created_coroutines.append(coro)
        mock_create_task.side_effect = side_effect

        # Mock a successful screen capture.
        test_image = Image.new('RGB', (100, 50), 'white')
        capture_result = CaptureResult(image=test_image, rectangle=(0, 0, 100, 50), success=True)
        
        def mock_capture_side_effect(on_capture_complete):
            on_capture_complete(capture_result)
            return True
        mock_capture.side_effect = mock_capture_side_effect

        # --- 2. Test Execution ---
        self.app._on_translate_hotkey()

        # Await the coroutine that was scheduled by the hotkey handler.
        self.assertEqual(len(created_coroutines), 1, "A coroutine should have been scheduled.")
        await created_coroutines[0]

        # --- 3. Assertions ---
        
        # a) Verify screen capture was called.
        mock_capture.assert_called_once()

        # b) Verify the async OCR processing stage was called.
        self.app._process_ocr_async.assert_awaited_once()

        # c) Verify the arguments passed to the OCR stage.
        call_args = self.app._process_ocr_async.call_args.args
        self.assertIsInstance(call_args[0], OCRRequest, "First argument should be an OCRRequest")
        self.assertEqual(call_args[0].image, test_image, "The correct image should be passed")
        self.assertEqual(call_args[1], capture_result, "The correct capture result should be passed")

        # d) Verify tray icon status was managed correctly.
        self.app.update_tray_status.assert_any_call(is_active=True)
        self.app.update_tray_status.assert_called_with(is_active=False)

if __name__ == '__main__':
    unittest.main()