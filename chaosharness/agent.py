from dataclasses import dataclass
from typing import Any
import json
import time

from .client import LLMClient, ToolCall
from .parsing import extract_json

@dataclass
class Step:
    index: int
    model_text: str
    tool_call: ToolCall | None
    tool_result_delivered: Any | None
    latency_s: float

@dataclass
class Episode:
    steps: list[Step]
    final: dict | None
    final_raw: str
    escalated: bool
    tool_calls_made: list[str]
    invalid_calls: int
    error: str | None

def run_episode(
    client: LLMClient,
    system_prompt: str,
    user_task: str,
    tools: list[dict],
    executor: Any,
    max_steps: int = 8,
    hint: dict | None = None,
    mock_hint: dict | None = None,
) -> Episode:
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_task}
    ]
    
    steps = []
    final_dict = None
    final_raw = ""
    escalated = False
    tool_calls_made = []
    invalid_calls = 0
    error = None
    
    for idx in range(max_steps):
        resp = client.chat(messages, tools=tools, hint=hint, mock_hint=mock_hint)
        
        if resp.error:
            error = resp.error
            steps.append(Step(idx, resp.text, None, None, resp.latency_s))
            break
            
        messages.append({"role": "assistant", "content": resp.text, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.args)}} for tc in resp.tool_calls]})
        
        for tc in resp.tool_calls:
            if getattr(tc, "invalid", False):
                invalid_calls += 1

        # Check if we have a final JSON answer in the text
        try:
            parsed = extract_json(resp.text)
            if isinstance(parsed, dict) and "final" in parsed:
                final_dict = parsed["final"]
                final_raw = resp.text
                steps.append(Step(idx, resp.text, None, None, resp.latency_s))
                break
        except Exception:
            pass
            
        if not resp.tool_calls:
            # no tool calls and no final answer -> error or stopped
            steps.append(Step(idx, resp.text, None, None, resp.latency_s))
            break
            
        # Execute first tool call
        tc = resp.tool_calls[0]
        tool_calls_made.append(tc.name)
        
        if tc.name == "escalate":
            escalated = True
            
        try:
            result = executor.execute(tc.name, tc.args)
            delivered = result
        except Exception as e:
            invalid_calls += 1
            delivered = {"error": str(e)}
            
        steps.append(Step(idx, resp.text, tc, delivered, resp.latency_s))
        
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "name": tc.name,
            "content": json.dumps(delivered)
        })

    return Episode(
        steps=steps,
        final=final_dict,
        final_raw=final_raw,
        escalated=escalated,
        tool_calls_made=tool_calls_made,
        invalid_calls=invalid_calls,
        error=error
    )
