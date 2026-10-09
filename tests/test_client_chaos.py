import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytest

from chaosharness.client import LLMClient, ToolCall, Response
from chaosharness.cache import RequestCache, CacheMiss

class MockHTTPHandler(BaseHTTPRequestHandler):
    # Class-level state for controlling mock responses
    responses = []
    requests_received = []

    def log_message(self, format, *args):
        pass # Suppress server logging during tests

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        MockHTTPHandler.requests_received.append({
            "path": self.path,
            "body": json.loads(body) if body else {}
        })

        if not MockHTTPHandler.responses:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"No response configured")
            return

        resp_config = MockHTTPHandler.responses.pop(0)
        status = resp_config.get("status", 200)
        headers = resp_config.get("headers", {})
        delay = resp_config.get("delay", 0)
        if delay > 0:
            time.sleep(delay)

        self.send_response(status)
        for h_k, h_v in headers.items():
            self.send_header(h_k, h_v)
        self.send_header("Content-Type", resp_config.get("content_type", "application/json"))
        self.end_headers()

        data = resp_config.get("body", "")
        if isinstance(data, dict):
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif isinstance(data, str):
            self.wfile.write(data.encode("utf-8"))
        elif isinstance(data, bytes):
            self.wfile.write(data)

    def do_GET(self):
        MockHTTPHandler.requests_received.append({"path": self.path, "method": "GET"})
        if not MockHTTPHandler.responses:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
            return

        resp_config = MockHTTPHandler.responses.pop(0)
        status = resp_config.get("status", 200)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = resp_config.get("body", {})
        if isinstance(body, dict):
            self.wfile.write(json.dumps(body).encode("utf-8"))
        else:
            self.wfile.write(str(body).encode("utf-8"))

@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockHTTPHandler)
    host, port = server.server_address
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    endpoint = f"http://127.0.0.1:{port}"
    yield endpoint
    server.shutdown()
    server.server_close()

@pytest.fixture(autouse=True)
def reset_server_state():
    MockHTTPHandler.responses = []
    MockHTTPHandler.requests_received = []

def test_client_200_success(mock_server):
    MockHTTPHandler.responses = [{
        "status": 200,
        "body": {
            "choices": [{"message": {"content": "Hello World"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
    }]
    client = LLMClient("test-model", mock_server, max_retries=1, backoff_s=0.01)
    resp = client.chat([{"role": "user", "content": "hi"}])
    assert resp.error is None
    assert resp.text == "Hello World"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.latency_s > 0

def test_client_400_bad_request_no_retries(mock_server):
    MockHTTPHandler.responses = [{
        "status": 400,
        "body": "Invalid parameters"
    }]
    client = LLMClient("test-model", mock_server, max_retries=3, backoff_s=0.01)
    resp = client.chat([{"role": "user", "content": "bad"}])
    assert resp.error is not None
    assert "HTTP 400" in resp.error
    # Must NOT retry permanent client errors
    assert len(MockHTTPHandler.requests_received) == 1

def test_client_401_unauthorized_no_retries(mock_server):
    MockHTTPHandler.responses = [{"status": 401, "body": "Unauthorized"}]
    client = LLMClient("test-model", mock_server, max_retries=3, backoff_s=0.01)
    resp = client.chat([{"role": "user", "content": "auth"}])
    assert resp.error is not None
    assert "HTTP 401" in resp.error
    assert len(MockHTTPHandler.requests_received) == 1

def test_client_429_rate_limit_with_retry_recovery(mock_server):
    MockHTTPHandler.responses = [
        {"status": 429, "body": "Rate limited"},
        {
            "status": 200,
            "body": {"choices": [{"message": {"content": "Recovered"}}], "usage": {"completion_tokens": 2}}
        }
    ]
    client = LLMClient("test-model", mock_server, max_retries=2, backoff_s=0.01)
    resp = client.chat([{"role": "user", "content": "throttle"}])
    assert resp.error is None
    assert resp.text == "Recovered"
    assert len(MockHTTPHandler.requests_received) == 2

def test_client_503_service_unavailable_exhaustion(mock_server):
    MockHTTPHandler.responses = [
        {"status": 503, "body": "Unavailable 1"},
        {"status": 503, "body": "Unavailable 2"}
    ]
    client = LLMClient("test-model", mock_server, max_retries=1, backoff_s=0.01)
    resp = client.chat([{"role": "user", "content": "busy"}])
    assert resp.error is not None
    assert "HTTP 503" in resp.error
    assert len(MockHTTPHandler.requests_received) == 2

def test_client_timeout_enforced(mock_server):
    MockHTTPHandler.responses = [{
        "status": 200,
        "delay": 0.5,
        "body": {"choices": [{"message": {"content": "Slow"}}]}
    }]
    client = LLMClient("test-model", mock_server, timeout_s=0.1, max_retries=0)
    resp = client.chat([{"role": "user", "content": "timeout"}])
    assert resp.error is not None

def test_client_malformed_json_response(mock_server):
    MockHTTPHandler.responses = [{
        "status": 200,
        "body": "Not Valid JSON {{{{"
    }]
    client = LLMClient("test-model", mock_server, max_retries=0)
    resp = client.chat([{"role": "user", "content": "json_error"}])
    assert resp.error is not None

def test_client_empty_choices(mock_server):
    MockHTTPHandler.responses = [{
        "status": 200,
        "body": {"choices": []}
    }]
    client = LLMClient("test-model", mock_server, max_retries=0)
    resp = client.chat([{"role": "user", "content": "empty"}])
    assert resp.error == "No choices returned"

def test_client_tool_call_extraction(mock_server):
    MockHTTPHandler.responses = [{
        "status": 200,
        "body": {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_123",
                        "function": {
                            "name": "get_ticket",
                            "arguments": "{\"ticket_id\": \"T-1042\"}"
                        }
                    }]
                }
            }],
            "usage": {"completion_tokens": 10}
        }
    }]
    client = LLMClient("test-model", mock_server)
    resp = client.chat(
        messages=[{"role": "user", "content": "lookup T-1042"}],
        tools=[{"type": "function", "function": {"name": "get_ticket"}}]
    )
    assert resp.error is None
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].id == "call_123"
    assert resp.tool_calls[0].name == "get_ticket"
    assert resp.tool_calls[0].args == {"ticket_id": "T-1042"}

def test_client_multimodal_image_encoding(mock_server):
    MockHTTPHandler.responses = [{
        "status": 200,
        "body": {"choices": [{"message": {"content": "Found square"}}]}
    }]
    client = LLMClient("test-model", mock_server)
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    resp = client.chat(
        messages=[{"role": "user", "content": "What is in image?"}],
        images=[fake_png]
    )
    assert resp.error is None
    sent_payload = MockHTTPHandler.requests_received[0]["body"]
    user_content = sent_payload["messages"][0]["content"]
    assert isinstance(user_content, list)
    assert any(item.get("type") == "image_url" for item in user_content)


def test_client_probe_and_record_metadata(tmp_path, mock_server):
    # Mock /api/tags
    MockHTTPHandler.responses = [
        {"status": 200, "body": {"models": [{"name": "test-model"}]}}, # /api/tags
        {"status": 200, "body": {"choices": [{"message": {"content": "5"}}]}} # tool probe
    ]
    cache = RequestCache(str(tmp_path), mode="record", model="test-model")
    client = LLMClient("test-model", mock_server, cache=cache)
    probe = client.probe()
    assert probe["reachable"] is True
    assert probe["model_available"] is True
    
    # Verify metadata saved to disk
    cached_meta = cache.get_probe_metadata()
    assert cached_meta is not None
    assert cached_meta["reachable"] is True
    assert cached_meta["model_available"] is True
