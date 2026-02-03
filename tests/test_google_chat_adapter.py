"""
Unit tests for GoogleChatClientAdapter.

Tests validate key behaviors without hitting real network.
"""

import base64
import pytest
from types import SimpleNamespace

from whisperbridge.providers.google_chat_adapter import GoogleChatClientAdapter


@pytest.fixture
def fake_google_client():
    """Create a fake Google GenAI client for testing."""
    adapter = GoogleChatClientAdapter(api_key="fake-key-for-testing", timeout=30)
    return adapter


@pytest.fixture
def mock_generate_content_response(mocker):
    """Create a mock response from generate_content."""
    mock_response = mocker.Mock()
    mock_response.text = "Test response text"
    
    # Mock usage metadata
    mock_usage = mocker.Mock()
    mock_usage.total_token_count = 100
    mock_usage.input_token_count = 50
    mock_usage.output_token_count = 50
    mock_response.usage_metadata = mock_usage
    
    return mock_response


class TestTextOnlyRequests:
    """Tests for text-only chat completion requests."""
    
    def test_text_only_success(self, mocker, fake_google_client, mock_generate_content_response):
        """Test text-only request returns expected response."""
        # Setup
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        mocker.patch.object(fake_google_client._client.models, 'generate_content', return_value=mock_generate_content_response)
        
        # Action
        response = fake_google_client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=messages,
            temperature=0.7,
            max_completion_tokens=256
        )
        
        # Assertions
        assert response.choices[0].message.content == "Test response text"
        assert response.usage.total_tokens == 100
    
    def test_text_only_with_thinking_config(self, mocker, fake_google_client, mock_generate_content_response):
        """Test that ThinkingConfig is set for Gemini 3 models."""
        # Setup
        messages = [{"role": "user", "content": "Test"}]
        
        mock_gen = mocker.patch.object(fake_google_client._client.models, 'generate_content', return_value=mock_generate_content_response)
        
        # Action
        response = fake_google_client.chat.completions.create(
            model="gemini-3-flash",
            messages=messages,
            temperature=0.7,
            max_completion_tokens=256
        )
        
        # Assertions
        assert mock_gen.called
        call_args = mock_gen.call_args
        config = call_args.kwargs.get('config')
        assert config is not None
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_level == fake_google_client._types.ThinkingLevel.LOW


class TestMultimodalRequests:
    """Tests for multimodal (text + image) completion requests."""
    
    def test_multimodal_jpeg_success(self, mocker, fake_google_client, mock_generate_content_response):
        """Test multimodal request with JPEG image returns expected response."""
        # Setup
        # Create a small JPEG image (1x1 pixel, red)
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x03\x02\x02\x03\x02\x02\x03\x03\x03\x03\x04\x03\x03\x04\x05\x08\x05\x05\x04\x04\x05\n\x07\x07\x06\x08\x0c\n\x0c\x0c\x0b\n\x0b\x0b\r\x0e\x12\x10\r\x0e\x11\x0e\x0b\x0b\x10\x16\x10\x11\x13\x14\x15\x15\x15\x0c\x0f\x17\x18\x16\x14\x18\x12\x14\x15\x14\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\n\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\x9f\xff\xd9'
        jpeg_b64 = base64.b64encode(jpeg_data).decode('utf-8')
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64}"}}
                ]
            }
        ]
        
        # Mock Part.from_bytes to capture mime_type
        mock_part = mocker.Mock()
        mock_from_bytes = mocker.patch.object(
            fake_google_client._types.Part,
            'from_bytes',
            return_value=mock_part
        )
        
        mock_gen = mocker.patch.object(fake_google_client._client.models, 'generate_content', return_value=mock_generate_content_response)
        
        # Action
        response = fake_google_client.chat.completions.create(
            model="gemini-2.0-flash-exp",
            messages=messages,
            temperature=0.7,
            max_completion_tokens=256
        )
        
        # Assertions
        assert response.choices[0].message.content == "Test response text"
        assert mock_gen.called
        
        # Verify Part.from_bytes was called with correct mime_type
        assert mock_from_bytes.called
        call_kwargs = mock_from_bytes.call_args.kwargs
        assert call_kwargs['mime_type'] == 'image/jpeg'
        assert call_kwargs['data'] == jpeg_data
    
    def test_multimodal_png_success(self, mocker, fake_google_client, mock_generate_content_response):
        """Test multimodal request with PNG image returns expected response."""
        # Setup
        # Create a small PNG image (1x1 pixel, red)
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        png_b64 = base64.b64encode(png_data).decode('utf-8')
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}}
                ]
            }
        ]
        
        # Mock Part.from_bytes to capture mime_type
        mock_part = mocker.Mock()
        mock_from_bytes = mocker.patch.object(
            fake_google_client._types.Part,
            'from_bytes',
            return_value=mock_part
        )
        
        mock_gen = mocker.patch.object(fake_google_client._client.models, 'generate_content', return_value=mock_generate_content_response)
        
        # Action
        response = fake_google_client.chat.completions.create(
            model="gemini-2.0-flash-exp",
            messages=messages,
            temperature=0.7,
            max_completion_tokens=256
        )
        
        # Assertions
        assert response.choices[0].message.content == "Test response text"
        assert mock_gen.called
        call_args = mock_gen.call_args
        contents = call_args.kwargs.get('contents')
        assert contents is not None
        assert len(contents) == 2  # text and image
        
        # Verify Part.from_bytes was called with correct PNG mime_type
        assert mock_from_bytes.called
        call_kwargs = mock_from_bytes.call_args.kwargs
        assert call_kwargs['mime_type'] == 'image/png'
        assert call_kwargs['data'] == png_data
    
    def test_multimodal_with_thinking_config(self, mocker, fake_google_client, mock_generate_content_response):
        """Test that ThinkingConfig is set for Gemini 3 models in multimodal requests."""
        # Setup
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        jpeg_b64 = base64.b64encode(jpeg_data).decode('utf-8')
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64}"}}
                ]
            }
        ]
        
        # Mock Part.from_bytes to capture mime_type
        mock_part = mocker.Mock()
        mock_from_bytes = mocker.patch.object(
            fake_google_client._types.Part,
            'from_bytes',
            return_value=mock_part
        )
        
        mock_gen = mocker.patch.object(fake_google_client._client.models, 'generate_content', return_value=mock_generate_content_response)
        
        # Action
        response = fake_google_client.chat.completions.create(
            model="gemini-3-flash",
            messages=messages,
            temperature=0.7,
            max_completion_tokens=256
        )
        
        # Assertions
        assert response.choices[0].message.content == "Test response text"
        assert mock_gen.called
        call_args = mock_gen.call_args
        contents = call_args.kwargs.get('contents')
        assert contents is not None
        assert len(contents) == 2  # text and image
        
        # Verify ThinkingConfig is set
        config = call_args.kwargs.get('config')
        assert config is not None
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_level == fake_google_client._types.ThinkingLevel.LOW
        
        # Verify Part.from_bytes was called with correct mime_type
        assert mock_from_bytes.called
        call_kwargs = mock_from_bytes.call_args.kwargs
        assert call_kwargs['mime_type'] == 'image/jpeg'
        assert call_kwargs['data'] == jpeg_data


class TestParseDataUrl:
    """Tests for the _parse_data_url method."""
    
    def test_parse_jpeg_data_url(self, fake_google_client):
        """Test parsing JPEG data URL."""
        # Setup
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        jpeg_b64 = base64.b64encode(jpeg_data).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{jpeg_b64}"
        
        # Action
        decoded_data, mime_type = fake_google_client._parse_data_url(data_url)
        
        # Assertions
        assert decoded_data == jpeg_data
        assert mime_type == "image/jpeg"
    
    def test_parse_png_data_url(self, fake_google_client):
        """Test parsing PNG data URL."""
        # Setup
        png_data = b'\x89PNG\r\n\x1a\n'
        png_b64 = base64.b64encode(png_data).decode('utf-8')
        data_url = f"data:image/png;base64,{png_b64}"
        
        # Action
        decoded_data, mime_type = fake_google_client._parse_data_url(data_url)
        
        # Assertions
        assert decoded_data == png_data
        assert mime_type == "image/png"
    
    def test_parse_webp_data_url(self, fake_google_client):
        """Test parsing WebP data URL."""
        # Setup
        webp_data = b'RIFF\x18\x00\x00\x00WEBPVP8'
        webp_b64 = base64.b64encode(webp_data).decode('utf-8')
        data_url = f"data:image/webp;base64,{webp_b64}"
        
        # Action
        decoded_data, mime_type = fake_google_client._parse_data_url(data_url)
        
        # Assertions
        assert decoded_data == webp_data
        assert mime_type == "image/webp"
    
    def test_parse_invalid_data_url_format(self, fake_google_client):
        """Test parsing invalid data URL format."""
        # Setup
        invalid_url = "not-a-data-url"
        
        # Action & Assertions
        with pytest.raises(ValueError, match="Invalid data URL format"):
            fake_google_client._parse_data_url(invalid_url)
    
    def test_parse_non_image_mime_type(self, fake_google_client):
        """Test parsing non-image MIME type."""
        # Setup
        data = b"test data"
        data_b64 = base64.b64encode(data).decode('utf-8')
        data_url = f"data:text/plain;base64,{data_b64}"
        
        # Action & Assertions
        with pytest.raises(ValueError, match="Unsupported MIME type"):
            fake_google_client._parse_data_url(data_url)
    
    def test_parse_empty_data_url(self, fake_google_client):
        """Test parsing empty data URL."""
        # Setup
        data_url = "data:image/jpeg;base64,"
        
        # Action & Assertions
        with pytest.raises(ValueError, match="Invalid data URL format"):
            fake_google_client._parse_data_url(data_url)
    
    def test_parse_invalid_base64(self, fake_google_client):
        """Test parsing invalid base64 data."""
        # Setup
        data_url = "data:image/jpeg;base64,!!!invalid!!!"
        
        # Action & Assertions
        with pytest.raises(ValueError, match="Failed to decode base64 data"):
            fake_google_client._parse_data_url(data_url)
    
    def test_parse_oversized_data_url(self, fake_google_client):
        """Test that oversized data URLs are rejected (DoS protection)."""
        # Setup - create a data URL exceeding 10MB
        # We don't actually need 10MB of real data, just a string that's too long
        large_data = "A" * (11 * 1024 * 1024)  # 11MB of 'A' characters
        data_url = f"data:image/jpeg;base64,{large_data}"
        
        # Action & Assertions
        with pytest.raises(ValueError, match="Data URL exceeds maximum size"):
            fake_google_client._parse_data_url(data_url)
    
    def test_parse_data_url_with_prefix_junk(self, fake_google_client):
        """Test that data URLs with prefix junk are rejected (regex anchor protection)."""
        # Setup
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        jpeg_b64 = base64.b64encode(jpeg_data).decode('utf-8')
        data_url = f"junk_prefix_data:image/jpeg;base64,{jpeg_b64}"
        
        # Action & Assertions
        with pytest.raises(ValueError, match="Invalid data URL format"):
            fake_google_client._parse_data_url(data_url)
    
    def test_parse_data_url_with_suffix_junk(self, fake_google_client):
        """Test that data URLs with suffix junk cause base64 decode error."""
        # Setup
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        jpeg_b64 = base64.b64encode(jpeg_data).decode('utf-8')
        # Add invalid base64 characters as suffix
        data_url = f"data:image/jpeg;base64,{jpeg_b64}!!!"
        
        # Action & Assertions
        # Suffix is matched by .+ but fails strict base64 validation
        with pytest.raises(ValueError, match="Failed to decode base64 data"):
            fake_google_client._parse_data_url(data_url)
