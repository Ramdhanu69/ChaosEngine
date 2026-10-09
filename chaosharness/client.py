import time
import json
import io
import requests
from dataclasses import dataclass
from typing import Any
from PIL import Image, ImageDraw

@dataclass
class ToolCall:
    id: str
    name: str
    args: dict
    invalid: bool = False

@dataclass
class Response:
    text: str
    tool_calls: list[ToolCall]
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    tokens_per_s: float
    raw: dict
    error: str | None
    truncated: bool = False

class LLMClient:
    def __init__(
        self,
        model: str,
        endpoint: str,
        temperature: float = 0.0,
        seed: int | None = None,
        max_tokens: int = 2048,
        timeout_s: float = 120,
        cache: Any = None,
        max_retries: int = 3,
        backoff_s: float = 0.5,
    ):
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.temperature = temperature
        self.seed = seed
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.cache = cache
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        
    def _do_request(self, payload: dict) -> tuple[dict, float, str | None]:
        url = f"{self.endpoint}/v1/chat/completions" if not self.endpoint.endswith("/v1/chat/completions") else self.endpoint
        
        start = time.perf_counter()
        backoff = self.backoff_s
        last_error = "Unknown error"
        
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout_s)
                # Non-retryable permanent client errors
                if resp.status_code in (400, 401, 403, 404):
                    latency_s = time.perf_counter() - start
                    return {}, latency_s, f"HTTP {resp.status_code}: {resp.text}"
                    
                if resp.status_code == 429 or resp.status_code in (500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    if attempt < self.max_retries:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    else:
                        latency_s = time.perf_counter() - start
                        return {}, latency_s, last_error
                        
                resp.raise_for_status()
                latency_s = time.perf_counter() - start
                return resp.json(), latency_s, None
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    latency_s = time.perf_counter() - start
                    return {}, latency_s, last_error
                    
        return {}, time.perf_counter() - start, last_error

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        images: list[bytes] | None = None,
        hint: dict | None = None,
        mock_hint: dict | None = None,
    ) -> Response:
        
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

        if self.cache:
            cached_resp = self.cache.get(payload, hint)
            if cached_resp:
                raw = cached_resp["raw"]
                latency_s = cached_resp["latency_s"]
                err = cached_resp["error"]
            else:
                raw, latency_s, err = self._do_request(payload)
                self.cache.put(payload, hint, {
                    "raw": raw,
                    "latency_s": latency_s,
                    "error": err
                })
        else:
            raw, latency_s, err = self._do_request(payload)
        
        if err:
            return Response(
                text="",
                tool_calls=[],
                latency_s=latency_s,
                prompt_tokens=0,
                completion_tokens=0,
                tokens_per_s=0.0,
                raw=raw,
                error=err,
                truncated=False
            )
            
        choices = raw.get("choices", [])
        if not choices:
            return Response("", [], latency_s, 0, 0, 0.0, raw, "No choices returned", False)
            
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        truncated = (finish_reason == "length")
        
        message = choice.get("message", {})
        text = message.get("content") or ""
        
        raw_tool_calls = message.get("tool_calls", [])
        tool_calls = []
        for tc in raw_tool_calls:
            try:
                fn = tc.get("function", {})
                args = json.loads(fn.get("arguments", "{}"))
                tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), args=args, invalid=False))
            except Exception:
                tool_calls.append(ToolCall(id=tc.get("id", ""), name=tc.get("function", {}).get("name", "unknown"), args={}, invalid=True))
                
        usage = raw.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        
        tokens_per_s = completion_tokens / latency_s if latency_s > 0 else 0.0
        
        return Response(
            text=text,
            tool_calls=tool_calls,
            latency_s=latency_s,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tokens_per_s=tokens_per_s,
            raw=raw,
            error=None,
            truncated=truncated
        )

    def probe(self) -> dict:
        if self.cache and hasattr(self.cache, "mode") and self.cache.mode == "replay":
            cached_meta = self.cache.get_probe_metadata()
            if cached_meta:
                return cached_meta

        reasons = {}
        result = {
            "reachable": False,
            "model_available": False,
            "native_tools": False,
            "json_mode": False,
            "vision": False,
            "ctx_hint": 4096,
            "reasons": reasons
        }
        
        try:
            if "localhost" in self.endpoint or "127.0.0.1" in self.endpoint:
                resp = requests.get(f"{self.endpoint}/api/tags", timeout=5)
                result["reachable"] = resp.status_code == 200
                if result["reachable"]:
                    tags = resp.json()
                    models = [m.get("name") for m in tags.get("models", [])]
                    result["model_available"] = any(self.model == m or m == f"{self.model}:latest" for m in models)
                    if not result["model_available"]:
                        reasons["model_available"] = f"Model '{self.model}' not in available tags: {models}"
                else:
                    reasons["reachable"] = f"GET /api/tags returned status {resp.status_code}"
            else:
                resp = requests.get(f"{self.endpoint}/v1/models", timeout=5)
                result["reachable"] = resp.status_code == 200
                if result["reachable"]:
                    models = [m.get("id") for m in resp.json().get("data", [])]
                    result["model_available"] = self.model in models
                    if not result["model_available"]:
                        reasons["model_available"] = f"Model '{self.model}' not in /v1/models: {models}"
                else:
                    reasons["reachable"] = f"GET /v1/models returned status {resp.status_code}"
        except Exception as e:
            reasons["reachable"] = f"Endpoint connection failed: {e}"
            return result
            
        if not result["model_available"]:
            return result
            
        # Probe native tools
        tool_probe = self.chat(
            messages=[{"role": "user", "content": "Add 2 and 3."}],
            tools=[{"type": "function", "function": {"name": "add", "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}}}}]
        )
        if tool_probe.error is None and tool_probe.tool_calls:
            result["native_tools"] = True
        else:
            reasons["native_tools"] = f"Tool call probe failed or returned no tools: {tool_probe.error or tool_probe.text}"
            
        # Probe json_mode
        json_probe = self.chat(
            messages=[{"role": "user", "content": "Respond ONLY with valid JSON: {\"status\": \"ok\"}"}]
        )
        if json_probe.error is None and "{" in json_probe.text and "}" in json_probe.text:
            result["json_mode"] = True
        else:
            reasons["json_mode"] = f"JSON mode probe failed: {json_probe.error or json_probe.text}"
            
        # Probe vision by rendering a tiny 64x64 PNG with a red square
        try:
            img = Image.new("RGB", (64, 64), color="white")
            d = ImageDraw.Draw(img)
            d.rectangle([10, 10, 50, 50], fill="red")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            
            vision_probe = self.chat(
                messages=[{"role": "user", "content": "What color is the square in this image?"}],
                images=[buf.getvalue()]
            )
            if vision_probe.error is None and "red" in vision_probe.text.lower():
                result["vision"] = True
            else:
                result["vision"] = False
                reasons["vision"] = f"Vision probe failed or answer did not mention red: {vision_probe.error or vision_probe.text}"
        except Exception as e:
            result["vision"] = False
            reasons["vision"] = f"Vision probe exception: {e}"
            
        if self.cache and hasattr(self.cache, "mode") and self.cache.mode == "record":
            self.cache.save_probe_metadata(result)
            
        return result
