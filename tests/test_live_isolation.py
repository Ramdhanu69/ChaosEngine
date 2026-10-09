import pytest
from unittest.mock import MagicMock, patch

from chaosharness.cli import get_client
from chaosharness.client import LLMClient

def test_live_mode_constructs_client_with_none_cache():
    client = get_client(
        model="gemma4:e2b",
        endpoint="http://localhost:11434",
        mock=None,
        cache_mode="live",
        cache_dir="./cache",
        seed=42,
        temp=0.0
    )
    assert isinstance(client, LLMClient)
    assert client.cache is None

def test_live_mode_calls_requests_post_and_never_cache_or_mocks():
    client = get_client(
        model="gemma4:e2b",
        endpoint="http://localhost:11434",
        mock=None,
        cache_mode="live",
        cache_dir="./cache",
        seed=42,
        temp=0.0
    )
    assert client.cache is None

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "Live response", "tool_calls": []}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2}
    }

    with patch("requests.post", return_value=fake_response) as mock_post, \
         patch("chaosharness.mocks.MockGood.chat") as mock_good_chat:
        resp = client.chat([{"role": "user", "content": "Hello live"}])
        
        assert resp.error is None
        assert resp.text == "Live response"
        assert mock_post.called
        assert not mock_good_chat.called
