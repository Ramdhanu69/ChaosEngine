import os
import pytest
import requests

from chaosharness.client import LLMClient

def is_ollama_ready():
    if os.environ.get("CHAOSHARNESS_TEST_LIVE") != "1":
        return False
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.0)
        if r.status_code == 200:
            models = [m.get("name") for m in r.json().get("models", [])]
            return any("gemma4:e2b" in m for m in models)
    except Exception:
        pass
    return False

@pytest.mark.live_ollama
@pytest.mark.skipif(not is_ollama_ready(), reason="Set CHAOSHARNESS_TEST_LIVE=1 with running local Ollama gemma4:e2b to run live test")
def test_live_ollama_capability_probe():
    client = LLMClient(
        model="gemma4:e2b",
        endpoint="http://127.0.0.1:11434",
        timeout_s=60.0
    )
    probe = client.probe()
    assert probe["reachable"] is True
    assert probe["model_available"] is True

@pytest.mark.live_ollama
@pytest.mark.skipif(not is_ollama_ready(), reason="Set CHAOSHARNESS_TEST_LIVE=1 with running local Ollama gemma4:e2b to run live test")
def test_live_ollama_small_prompt():
    client = LLMClient(
        model="gemma4:e2b",
        endpoint="http://127.0.0.1:11434",
        max_tokens=20,
        timeout_s=60.0
    )
    resp = client.chat([{"role": "user", "content": "Say hello in one word."}])
    assert resp.error is None
    assert len(resp.text.strip()) > 0
    assert resp.latency_s > 0

