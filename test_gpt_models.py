#!/usr/bin/env python3
"""
Test script for GPT models filtering.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_gpt_filtering():
    """Test GPT models filtering logic."""
    try:
        from whisperbridge.core.api_manager import get_api_manager, init_api_manager, APIProvider

        print("Testing GPT models filtering...")

        # Initialize API manager
        manager = init_api_manager()
        print(f"API manager initialized: {manager.is_initialized()}")

        # Test the filtering logic directly
        import asyncio

        async def test_filter():
            models_response = await manager._clients[APIProvider.OPENAI].models.list()

            # Test current filtering logic
            all_models = [model.id for model in models_response.data]
            print(f"All models from API: {len(all_models)}")
            print("Sample models:", all_models[:10])

            # Apply our filtering
            gpt_models = [
                model.id for model in models_response.data
                if model.id.lower().startswith("gpt")
            ]

            print(f"\nFiltered GPT models: {len(gpt_models)}")
            print("GPT models:", gpt_models)

            # Sort as in our code
            gpt_models.sort(key=lambda x: (x.lower().startswith("gpt-3"), x), reverse=True)
            print("\nSorted GPT models:", gpt_models)

            return gpt_models

        # Run the test
        gpt_models = asyncio.run(test_filter())

        print(f"\nFinal result: {len(gpt_models)} GPT models available")
        return gpt_models

    except Exception as e:
        print(f"Error in GPT filtering test: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    models = test_gpt_filtering()
    if models:
        print(f"\n✅ Successfully filtered {len(models)} GPT models")
    else:
        print("\n❌ Failed to filter GPT models")