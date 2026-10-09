import json
import re
from typing import Any

def clean_llm_text(text: str) -> str:
    if not text:
        return ""
    # Strip <think>...</think> blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Strip unclosed <think>... if truncated inside thinking block
    text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL)
    # Strip code fences ```json ... ``` or ``` ... ```
    text = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', text, flags=re.DOTALL)
    return text.strip()

def extract_json(text: str) -> Any:
    cleaned = clean_llm_text(text)
    if not cleaned:
        raise ValueError("Empty text after cleaning")

    # Try direct json.loads
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Try substring from first { to last }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace:last_brace + 1])
        except Exception:
            pass

    # Try substring from first [ to last ]
    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        try:
            return json.loads(cleaned[first_bracket:last_bracket + 1])
        except Exception:
            pass

    raise ValueError(f"Could not parse JSON from text: {text[:100]}...")
