import sys
import datetime
import json
from pathlib import Path
import requests

def build_provenance(args, client=None, probe=None, trials=None, items=None) -> dict:
    mock_val = getattr(args, "mock", None)
    cache_mode = getattr(args, "cache", "live")
    
    if mock_val:
        mode = "mock"
    elif cache_mode == "replay":
        mode = "replay"
    elif cache_mode == "record":
        mode = "record"
    else:
        mode = "live"
        
    cache_dir = getattr(args, "cache_dir", "./cache")
    cache_source = None
    meta_path = Path(cache_dir) / "probe_metadata.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                cache_source = meta.get("source")
        except Exception:
            pass

    synthetic = (mode == "mock") or (mode == "replay" and cache_source == "synthetic_mock_demo")

    model = getattr(args, "model", "unknown")
    endpoint = getattr(args, "endpoint", "")
    seed = getattr(args, "seed", 42)
    temp = getattr(args, "temperature", 0.0)
    
    quick_mode = getattr(args, "quick", False)
    if trials is None:
        trials = 2 if quick_mode else (getattr(args, "trials", 5) or 5)
    if items is None:
        items = 5 if quick_mode else (getattr(args, "items", 10) or 10)

    ollama_version = None
    model_digest = None

    if mode == "live" and endpoint:
        ep = endpoint.rstrip("/")
        # Best effort Ollama version check
        try:
            ver_resp = requests.get(f"{ep}/api/version", timeout=2)
            if ver_resp.status_code == 200:
                ollama_version = ver_resp.json().get("version")
        except Exception:
            pass

        # Best effort model digest check
        try:
            tags_resp = requests.get(f"{ep}/api/tags", timeout=2)
            if tags_resp.status_code == 200:
                models = tags_resp.json().get("models", [])
                for m in models:
                    name = m.get("name", "")
                    if name == model or name == f"{model}:latest":
                        model_digest = m.get("digest")
                        break
        except Exception:
            pass

    return {
        "mode": mode,
        "synthetic": synthetic,
        "model": model,
        "endpoint": endpoint,
        "seed": seed,
        "trials": trials,
        "items": items,
        "temperature": temp,
        "utc_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "harness_version": "1.0.0",
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "cache_dir": cache_dir,
        "cache_source": cache_source,
        "ollama_version": ollama_version,
        "model_digest": model_digest
    }
