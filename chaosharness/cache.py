import json
import hashlib
from pathlib import Path
from dataclasses import asdict
from typing import Any

class CacheMiss(Exception):
    pass

class RequestCache:
    def __init__(self, cache_dir: str = "./cache", mode: str = "live", model: str = "default"):
        # Handle positional arg swapping if mode is passed as first arg
        if cache_dir in ("live", "record", "replay") and mode not in ("live", "record", "replay"):
            mode, cache_dir = cache_dir, mode
            
        self.mode = mode
        self.cache_dir = Path(cache_dir)
        self.model = model
        self.cache_file = self.cache_dir / f"{model.replace(':', '_').replace('/', '_')}.jsonl"
        self._entries: dict[str, dict] = {}
        
        if self.mode in ("record", "replay"):
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self):
        if not self.cache_file.exists():
            return
        with open(self.cache_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    self._entries[entry["key"]] = entry["response"]
                except Exception:
                    pass

    def _save_entry(self, key: str, response: dict):
        self._entries[key] = response
        with open(self.cache_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "response": response}, sort_keys=True) + "\n")

    def _compute_key(self, payload: dict, hint: dict | None) -> str:
        cache_dict = {
            "payload": payload,
            "hint": hint
        }
        canonical = json.dumps(cache_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(self, payload: dict, hint: dict | None) -> dict | None:
        if self.mode == "live":
            return None
            
        key = self._compute_key(payload, hint)
        if key in self._entries:
            return self._entries[key]
            
        if self.mode == "replay":
            raise CacheMiss(f"Cache miss in replay mode for key {key}")
            
        return None

    def put(self, payload: dict, hint: dict | None, response_data: dict):
        if self.mode == "record":
            key = self._compute_key(payload, hint)
            if key not in self._entries:
                self._save_entry(key, response_data)

    def get_probe_metadata(self) -> dict | None:
        meta_file = self.cache_dir / "probe_metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def save_probe_metadata(self, probe_info: dict, recorded_with: dict | None = None):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        meta_file = self.cache_dir / "probe_metadata.json"
        data = dict(probe_info)
        if recorded_with:
            data["recorded_with"] = recorded_with
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
