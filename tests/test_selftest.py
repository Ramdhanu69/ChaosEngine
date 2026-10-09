import pytest
from chaosharness.cli import run_selftest
from chaosharness.mocks import MockGood, MockLooping, MockHallucinating, MockInjectable
from chaosharness.chaos import run_chaos_suite
from chaosharness.profiler import run_domain_suite
from chaosharness.synthesizer import build_routing_manifest
from chaosharness.scoring import FailureLabel

def test_selftest_command():
    """Verify that chaosharness selftest returns exit code 0."""
    exit_code = run_selftest()
    assert exit_code == 0

def test_mock_good_full_pass():
    """Verify MockGood achieves 100% resilience and AUTONOMOUS status across all domains."""
    client = MockGood()
    chaos = run_chaos_suite(client, seed=42, trials=2, quick=True, vectors=["all"], packs=[])
    domains = run_domain_suite(client, seed=42, items_per_domain=3, skip_vision=False)
    manifest = build_routing_manifest("mock-good", chaos, domains, seed=42, trials=2)

    assert manifest["overall_resilience"] == 100.0
    for dom in ["code_generation", "structured_data", "algorithmic_logic", "vision_processing"]:
        assert manifest["tiers"][dom] == "AUTONOMOUS"

def test_mock_looping_detection():
    """Verify MockLooping produces LOOP failures and does not claim recovery."""
    client = MockLooping()
    chaos = run_chaos_suite(client, seed=42, trials=2, quick=True, vectors=["retry_trap_503"], packs=[])
    fails = [r.failure_label for r in chaos if r.failure_label]
    assert FailureLabel.LOOP.value in fails

def test_mock_hallucinating_detection():
    """Verify MockHallucinating triggers HALLUCINATED_TOOL or FABRICATED_VALUE."""
    client = MockHallucinating()
    chaos = run_chaos_suite(client, seed=42, trials=2, quick=True, vectors=["phantom_tool_lure"], packs=[])
    fails = [r.failure_label for r in chaos if r.failure_label]
    assert any(label in fails for label in [FailureLabel.HALLUCINATED_TOOL.value, FailureLabel.FABRICATED_VALUE.value])

def test_mock_injectable_detection():
    """Verify MockInjectable triggers INJECTION_FOLLOWED and fails safety threshold."""
    client = MockInjectable()
    chaos = run_chaos_suite(client, seed=42, trials=2, quick=True, vectors=["prompt_injection"], packs=[])
    fails = [r.failure_label for r in chaos if r.failure_label]
    assert FailureLabel.INJECTION_FOLLOWED.value in fails
