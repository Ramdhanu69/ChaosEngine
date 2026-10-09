import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from chaosharness.cache import RequestCache
from chaosharness.mocks import MockGood
from chaosharness.chaos import run_chaos_suite
from chaosharness.profiler import run_domain_suite

def generate_demo_cache():
    cache_dir = Path(__file__).parent.parent / "demo_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Remove old gemma4_e2b.jsonl if present
    old_file = cache_dir / "gemma4_e2b.jsonl"
    if old_file.exists():
        old_file.unlink()
        
    model_name = "mock-good"
    cache = RequestCache(cache_dir=str(cache_dir), mode="record", model=model_name)
    
    recorded_with = {
        "seed": 42,
        "trials": 2,
        "items": 5,
        "quick": True,
        "vision": True,
        "model": model_name
    }
    
    probe_meta = {
        "reachable": True,
        "model_available": True,
        "native_tools": True,
        "json_mode": True,
        "vision": True,
        "ctx_hint": 4096,
        "source": "synthetic_mock_demo",
        "recorded_with": recorded_with,
        "reasons": {}
    }
    cache.save_probe_metadata(probe_meta, recorded_with=recorded_with)
    
    mock = MockGood()
    
    class RecordingClient:
        def __init__(self, inner, cache, model):
            self.inner = inner
            self.cache = cache
            self.model = model
            self.temperature = 0.0
            self.seed = 42
            self.max_tokens = 2048
            
        def probe(self):
            return self.inner.probe()
            
        def chat(self, messages, tools=None, images=None, hint=None, mock_hint=None):
            resp = self.inner.chat(messages, tools=tools, images=images, hint=hint, mock_hint=mock_hint)
            
            if images:
                import base64
                b64_urls = [f"data:image/png;base64,{base64.b64encode(img).decode('ascii')}" for img in images]
                payload_messages = []
                for m in messages:
                    if m.get("role") == "user":
                        content_parts = [{"type": "text", "text": m.get("content", "")}]
                        for url in b64_urls:
                            content_parts.append({"type": "image_url", "image_url": {"url": url}})
                        payload_messages.append({"role": "user", "content": content_parts})
                    else:
                        payload_messages.append(m)
            else:
                payload_messages = messages

            payload = {
                "model": self.model,
                "messages": payload_messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            if self.seed is not None:
                payload["seed"] = self.seed
            if tools:
                payload["tools"] = tools
                
            self.cache.put(payload, hint, {
                "raw": resp.raw,
                "latency_s": resp.latency_s,
                "error": resp.error
            })
            return resp

    rec_client = RecordingClient(mock, cache, model_name)
    
    print("[INFO] Generating synthetic offline demo cache for mock-good...")
    # 1. Quick Chaos
    run_chaos_suite(rec_client, seed=42, trials=2, quick=True, vectors=["all"], packs=[])
    # 2. Quick Domains
    run_domain_suite(rec_client, seed=42, items_per_domain=5, skip_vision=False)
    
    print(f"[PASS] Demo cache successfully generated in {cache_dir}")

if __name__ == "__main__":
    generate_demo_cache()
