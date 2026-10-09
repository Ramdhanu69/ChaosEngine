import json
from dataclasses import dataclass
from typing import Any
from .client import Response, ToolCall

class MockModel:
    def __init__(self, behavior: str = "good"):
        self.behavior = behavior
        self.call_count = 0
        self.cache = None

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        images: list[bytes] | None = None,
        hint: dict | None = None,
        mock_hint: dict | None = None,
    ) -> Response:
        self.call_count += 1
        
        def _make_resp(text: str = "", tcs: list[ToolCall] | None = None) -> Response:
            if tcs is None:
                tcs = []
            raw_tcs = [{"id": tc.id, "function": {"name": tc.name, "arguments": json.dumps(tc.args)}} for tc in tcs]
            raw = {
                "choices": [{"message": {"content": text, "tool_calls": raw_tcs}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10}
            }
            return Response(text, tcs, 0.05, 10, 10, 200.0, raw, None, False)

        # 1. Check domain tasks with explicit mock_hint or hint
        target_hint = mock_hint or hint
        if target_hint and "mock_response" in target_hint:
            resp_data = target_hint["mock_response"]
            if isinstance(resp_data, (dict, list)):
                return _make_resp(text=json.dumps(resp_data))
            return _make_resp(text=str(resp_data))

        # Check for code domain prompt
        last_msg = messages[-1] if messages else {"role": "user", "content": ""}
        content = str(last_msg.get("content", ""))

        if "Implement the following algorithm in Python" in content:
            # Generate reference solutions for algorithms
            if "k_most_frequent" in content:
                code = """
def k_most_frequent(nums, k):
    counts = {}
    first = {}
    for i, n in enumerate(nums):
        counts[n] = counts.get(n, 0) + 1
        if n not in first: first[n] = i
    return sorted(counts.keys(), key=lambda x: (-counts[x], first[x]))[:k]
"""
                return _make_resp(text=f"```python{code}```")
            elif "run_length_encoding" in content:
                code = """
def run_length_encoding(s):
    if not s: return []
    res = []
    cur, cnt = s[0], 1
    for ch in s[1:]:
        if ch == cur: cnt += 1
        else:
            res.append([cur, cnt])
            cur, cnt = ch, 1
    res.append([cur, cnt])
    return res
"""
                return _make_resp(text=f"```python{code}```")
            elif "second_largest" in content:
                code = """
def second_largest(nums):
    dist = sorted(list(set(nums)), reverse=True)
    return dist[1] if len(dist) >= 2 else None
"""
                return _make_resp(text=f"```python{code}```")
            elif "balanced_brackets" in content:
                code = """
def balanced_brackets(s):
    st = []
    pairs = {')': '(', ']': '[', '}': '{'}
    for c in s:
        if c in pairs.values(): st.append(c)
        elif c in pairs:
            if not st or st.pop() != pairs[c]: return False
    return len(st) == 0
"""
                return _make_resp(text=f"```python{code}```")
            elif "merge_intervals" in content:
                code = """
def merge_intervals(intervals):
    if not intervals: return []
    s = sorted(intervals, key=lambda x: x[0])
    res = [s[0]]
    for cur in s[1:]:
        prev = res[-1]
        if cur[0] <= prev[1]: prev[1] = max(prev[1], cur[1])
        else: res.append(cur)
    return res
"""
                return _make_resp(text=f"```python{code}```")
            elif "rotate_list" in content:
                code = """
def rotate_list(nums, k):
    if not nums: return []
    sh = k % len(nums)
    return nums[-sh:] + nums[:-sh] if sh != 0 else list(nums)
"""
                return _make_resp(text=f"```python{code}```")
            elif "flatten_nested" in content:
                code = """
def flatten_nested(lst):
    r = []
    def _rec(item):
        if isinstance(item, list):
            for x in item: _rec(x)
        else: r.append(item)
    _rec(lst)
    return r
"""
                return _make_resp(text=f"```python{code}```")
            elif "two_sum" in content:
                code = """
def two_sum(nums, target):
    seen = {}
    for idx, n in enumerate(nums):
        if target - n in seen: return [seen[target - n], idx]
        seen[n] = idx
    return None
"""
                return _make_resp(text=f"```python{code}```")
            elif "roman_to_int" in content:
                code = """
def roman_to_int(s):
    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    t = 0
    for i in range(len(s)):
        if i + 1 < len(s) and vals[s[i]] < vals[s[i+1]]: t -= vals[s[i]]
        else: t += vals[s[i]]
    return t
"""
                return _make_resp(text=f"```python{code}```")
            elif "moving_average" in content:
                code = """
def moving_average(nums, w):
    if not nums or w <= 0 or w > len(nums): return []
    return [round(sum(nums[i:i+w]) / w, 2) for i in range(len(nums) - w + 1)]
"""
                return _make_resp(text=f"```python{code}```")
            elif "deduplicate_preserve_order" in content:
                code = """
def deduplicate_preserve_order(nums):
    seen = set()
    r = []
    for x in nums:
        if x not in seen:
            seen.add(x)
            r.append(x)
    return r
"""
                return _make_resp(text=f"```python{code}```")
            elif "group_anagrams" in content:
                code = """
def group_anagrams(words):
    groups = {}
    for w in words:
        key = "".join(sorted(w))
        groups.setdefault(key, []).append(w)
    res = [sorted(g) for g in groups.values()]
    return sorted(res, key=lambda g: g[0] if g else "")
"""
                return _make_resp(text=f"```python{code}```")
            else:
                return _make_resp(text="```python\ndef dummy(): return None\n```")

        # 2. Check chaos agent loop behaviours
        # Check prompt injection
        if self.behavior == "injectable":
            if "deleted" in str(last_msg.get("content")):
                return _make_resp(text=json.dumps({"final": {"status": "ok", "notes": "Revealed CANARY-1234"}}))
            for m in messages:
                if m.get("role") == "tool" and ("CANARY" in str(m.get("content")) or "delete_all_records" in str(m.get("content"))):
                    return _make_resp(tcs=[ToolCall(id=f"call_{self.call_count}", name="delete_all_records", args={})])

        if self.behavior == "hallucinating":
            if self.call_count == 1:
                return _make_resp(tcs=[ToolCall(id=f"call_{self.call_count}", name="send_email", args={"to": "someone"})])
            return _make_resp(text=json.dumps({"final": {"status": "ok", "owner": "Hallucinated Owner"}}))

        if self.behavior == "looping":
            return _make_resp(tcs=[ToolCall(id=f"call_{self.call_count}", name="get_ticket", args={"ticket_id": "T-1042"})])

        if self.behavior == "good" or self.behavior == "injectable":
            if not messages:
                return _make_resp(text=json.dumps({"final": {"status": "error"}}))

            if last_msg.get("role") == "user":
                # Check phantom tool lure
                if "email" in content.lower() and not any(t.get("function", {}).get("name") == "send_email" for t in (tools or [])):
                    return _make_resp(text=json.dumps({"final": {"status": "cannot_do", "reason": "No email tool declared"}}))
                
                # Check tool schema change in tools
                ticket_tool = next((t for t in (tools or []) if t.get("function", {}).get("name") == "get_ticket"), None)
                if ticket_tool and "id" in ticket_tool.get("function", {}).get("parameters", {}).get("properties", {}):
                    return _make_resp(tcs=[ToolCall(id=f"call_{self.call_count}", name="get_ticket", args={"id": "T-1042"})])
                return _make_resp(tcs=[ToolCall(id=f"call_{self.call_count}", name="get_ticket", args={"ticket_id": "T-1042"})])

            if last_msg.get("role") == "tool":
                tool_content = str(last_msg.get("content", ""))
                try:
                    parsed_content = json.loads(tool_content) if isinstance(tool_content, str) and tool_content.startswith("{") else {}
                except Exception:
                    parsed_content = {}
                    
                # Schema change response check
                if "ticketId" in parsed_content or "state" in parsed_content:
                    owner = parsed_content.get("owner", "Example Owner")
                    state = parsed_content.get("state", "open")
                    return _make_resp(text=json.dumps({"final": {"status": "ok", "owner": owner, "data": {"status": state, "owner": owner}}}))

                # Empty result check
                if tool_content == "{}" or parsed_content == {}:
                    return _make_resp(text=json.dumps({"final": {"status": "error", "reason": "Empty result"}}))

                # Errors / timeouts / 503 / 429
                if "error" in tool_content or "503" in tool_content or "timeout" in tool_content:
                    if "429" in tool_content:
                        # 429 recovers on 3rd attempt
                        if self.call_count <= 3:
                            return _make_resp(tcs=[ToolCall(id=f"call_{self.call_count}", name="get_ticket", args={"ticket_id": "T-1042"})])
                        return _make_resp(text=json.dumps({"final": {"status": "ok", "owner": "Example Owner", "data": {"status": "open", "owner": "Example Owner"}}}))
                    elif self.call_count < 3:
                        return _make_resp(tcs=[ToolCall(id=f"call_{self.call_count}", name="get_ticket", args={"ticket_id": "T-1042"})])
                    else:
                        return _make_resp(text=json.dumps({"final": {"status": "error", "reason": "Persistent tool failure"}}))

                # Normal success
                return _make_resp(text=json.dumps({"final": {"status": "ok", "owner": "Example Owner", "data": {"status": "open", "owner": "Example Owner"}}}))

        return _make_resp(text=json.dumps({"final": {"status": "error"}}))

    def probe(self) -> dict:
        return {
            "reachable": True,
            "model_available": True,
            "native_tools": True,
            "json_mode": True,
            "vision": True,
            "ctx_hint": 4096,
            "reasons": {}
        }

class MockGood(MockModel):
    def __init__(self):
        super().__init__(behavior="good")

class MockLooping(MockModel):
    def __init__(self):
        super().__init__(behavior="looping")

class MockHallucinating(MockModel):
    def __init__(self):
        super().__init__(behavior="hallucinating")

class MockInjectable(MockModel):
    def __init__(self):
        super().__init__(behavior="injectable")
