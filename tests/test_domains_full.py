import json
import pytest

from chaosharness.domains.code import (
    algorithms,
    run_domain_code,
    run_code_item,
    extract_code
)
from chaosharness.domains.data import generate_messy_log, run_domain_data, flatten
from chaosharness.domains.logic import generate_logic_task, run_domain_logic, flatten_dict
from chaosharness.domains.vision import generate_vision_task, box_iou, run_domain_vision
from chaosharness.domains.sandbox import run_in_sandbox
from chaosharness.mocks import MockGood, MockModel
from chaosharness.scoring import FailureLabel
from chaosharness.profiler import run_domain_suite

# 1. Code Domain Full Verification
def test_all_12_code_algorithms_exist_and_generate_tests():
    assert len(algorithms) == 12
    algo_names = [a.name for a in algorithms]
    expected_names = [
        "k_most_frequent",
        "run_length_encoding",
        "second_largest",
        "balanced_brackets",
        "merge_intervals",
        "rotate_list",
        "flatten_nested",
        "two_sum",
        "roman_to_int",
        "moving_average",
        "deduplicate_preserve_order",
        "group_anagrams"
    ]
    for exp in expected_names:
        assert exp in algo_names

    for algo in algorithms:
        tests = algo.generate_tests(seed=42)
        assert len(tests) >= 3
        for args, expected in tests:
            assert args is not None

def test_code_suite_execution_with_mock_good():
    client = MockGood()
    items = run_domain_code(client, seed=42, items_count=12)
    assert len(items) == 12
    for it in items:
        assert it.passed is True
        assert it.score == 1.0

def test_code_extract_code_helper():
    text1 = "```python\ndef test(): return 1\n```"
    assert extract_code(text1) == "def test(): return 1"

    text2 = "```\ndef test(): return 2\n```"
    assert extract_code(text2) == "def test(): return 2"

    text3 = "def test(): return 3"
    assert extract_code(text3) == "def test(): return 3"

def test_code_flawed_implementation_detection():
    broken_code = "def k_most_frequent(nums, k): return []"
    class BrokenCodeMock:
        def chat(self, messages, tools=None, images=None, hint=None):
            from chaosharness.client import Response
            return Response(
                text=f"```python\n{broken_code}\n```",
                tool_calls=[],
                latency_s=0.01,
                prompt_tokens=10,
                completion_tokens=10,
                tokens_per_s=100.0,
                raw={},
                error=None
            )

    algo = algorithms[0]
    res = run_code_item(algo, seed=42, item_id="C-0", client=BrokenCodeMock())
    assert res.passed is False
    assert res.score == 0.0

def test_code_infinite_loop_timeout_detection():
    loop_code = "def k_most_frequent(nums, k):\n    while True:\n        pass\n    return []"
    class LoopCodeMock:
        def chat(self, messages, tools=None, images=None, hint=None):
            from chaosharness.client import Response
            return Response(
                text=f"```python\n{loop_code}\n```",
                tool_calls=[],
                latency_s=0.01,
                prompt_tokens=10,
                completion_tokens=10,
                tokens_per_s=100.0,
                raw={},
                error=None
            )

    algo = algorithms[0]
    res = run_code_item(algo, seed=42, item_id="C-0", client=LoopCodeMock())
    assert res.passed is False
    assert res.failure_label == FailureLabel.SANDBOX_TIMEOUT.value

# 2. Data Domain Verification
def test_data_task_generation():
    log_text, gt = generate_messy_log(seed=42)
    assert "Incident" in log_text
    assert "incident" in gt
    assert "metrics" in gt

def test_data_flatten():
    d = {"a": {"b": 1, "c": {"d": 2}}, "e": 3}
    flat = flatten(d)
    assert flat == {"a.b": 1, "a.c.d": 2, "e": 3}

def test_data_suite_with_mock_good():
    client = MockGood()
    items = run_domain_data(client, seed=42, items_count=3)
    assert len(items) == 3
    for it in items:
        assert it.passed is True
        assert it.score == 1.0

# 3. Logic Domain Verification
def test_logic_tasks_all_families():
    # Inventory
    p_inv, gt_inv = generate_logic_task(seed=42, family="inventory")
    assert "stock" in gt_inv
    assert "fulfilled" in gt_inv

    # Bank
    p_bank, gt_bank = generate_logic_task(seed=42, family="bank")
    assert "A" in gt_bank
    assert "B" in gt_bank
    assert "rejected" in gt_bank

    # Order
    p_order, gt_order = generate_logic_task(seed=42, family="order")
    assert "steps" in gt_order

def test_logic_flatten_dict():
    d = {"A": 100, "details": ["x", "y"]}
    flat = flatten_dict(d)
    assert flat["A"] == 100
    assert flat["details"] == "['x', 'y']"

def test_logic_suite_with_mock_good():
    client = MockGood()
    items = run_domain_logic(client, seed=42, items_count=3)
    assert len(items) == 3
    for it in items:
        assert it.passed is True
        assert it.score == 1.0

# 4. Vision Domain Verification
def test_vision_task_all_categories():
    for cat in ["grid", "box", "diagram"]:
        prompt, img_bytes, gt = generate_vision_task(seed=42, cat=cat)
        assert img_bytes.startswith(b"\x89PNG")
        assert isinstance(gt, dict)

def test_vision_box_iou():
    b1 = {"x": 10, "y": 10, "w": 40, "h": 40}
    b2 = {"x": 10, "y": 10, "w": 40, "h": 40}
    assert box_iou(b1, b2) == 1.0

    b3 = {"x": 100, "y": 100, "w": 20, "h": 20}
    assert box_iou(b1, b3) == 0.0

    # Overlapping box
    b4 = {"x": 30, "y": 30, "w": 40, "h": 40}
    iou = box_iou(b1, b4)
    assert 0.0 < iou < 1.0

def test_vision_suite_with_mock_good():
    client = MockGood()
    items = run_domain_vision(client, seed=42, items_count=3)
    assert len(items) == 3
    for it in items:
        assert it.passed is True
        assert it.score == 1.0

# 5. Full Profiler Orchestration
def test_run_domain_suite_full_orchestration():
    client = MockGood()
    res = run_domain_suite(
        client=client,
        seed=42,
        items_per_domain=2,
        skip_vision=False,
        domains_to_run=["code", "data", "logic", "vision"]
    )
    assert len(res) == 4
    for dom_key in ["code_generation", "structured_data", "algorithmic_logic", "vision_processing"]:
        assert dom_key in res
        d_res = res[dom_key]
        assert d_res.supported is True
        assert d_res.score == 100.0
        assert d_res.wilson_lower is not None
        assert d_res.wilson_upper is not None
