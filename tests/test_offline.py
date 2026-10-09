import pytest
import os
import json
import tempfile
from pathlib import Path

from chaosharness.generators import stable_seed
from chaosharness.scoring import (
    wilson_interval,
    calculate_overall_resilience,
    calculate_per_vector_resilience,
    calculate_silent_corruption_rate,
    FailureLabel,
    DomainResult,
    ItemResult
)
from chaosharness.cache import RequestCache, CacheMiss
from chaosharness.scenarios import load_yaml_pack, get_builtin_scenarios
from chaosharness.domains.sandbox import run_in_sandbox
from chaosharness.synthesizer import (
    build_routing_manifest,
    determine_domain_tier,
    derive_routing_constraints,
    determine_recommended_route,
    generate_radar_chart_svg,
    generate_svg_badge,
    DOMAIN_KEYS
)
from chaosharness.chaos import EpisodeResult
from chaosharness.mocks import MockGood

# 1. Determinism Tests
def test_stable_seed_determinism():
    s1 = stable_seed(42, "vector_a", 0)
    s2 = stable_seed(42, "vector_a", 0)
    assert s1 == s2
    assert isinstance(s1, int)
    assert s1 >= 0

def test_stable_seed_divergence():
    s1 = stable_seed(42, "vector_a", 0)
    s2 = stable_seed(42, "vector_a", 1)
    s3 = stable_seed(100, "vector_a", 0)
    assert s1 != s2
    assert s1 != s3

# 2. Scoring & Wilson Interval Tests
def test_wilson_interval_valid():
    point, low, high = wilson_interval(5, 10)
    assert round(point, 1) == 50.0
    assert 0.0 <= low <= point <= high <= 100.0

def test_wilson_interval_edge_cases():
    point, low, high = wilson_interval(0, 10)
    assert point == 0.0
    assert low == 0.0
    
    point_full, low_full, high_full = wilson_interval(10, 10)
    assert point_full == 100.0
    assert high_full == 100.0

def test_wilson_interval_invalid():
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)
    with pytest.raises(ValueError):
        wilson_interval(11, 10)
    with pytest.raises(ValueError):
        wilson_interval(5, 0)

def test_resilience_client_error_exclusion():
    episodes = [
        EpisodeResult("v1", 0, True, None, 1, 0.1, "pass"),
        EpisodeResult("v1", 1, False, FailureLabel.CLIENT_ERROR.value, 1, 0.1, "err"),
        EpisodeResult("v1", 2, False, FailureLabel.LOOP.value, 3, 0.3, "loop")
    ]
    # CLIENT_ERROR excluded from evaluable: 1 passed out of 2 evaluable = 50%
    unw, w, lcb = calculate_overall_resilience(episodes)
    assert unw == 50.0

# 3. Cache Record & Replay Tests
def test_cache_record_and_replay():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Record mode
        cache_rec = RequestCache(tmpdir, mode="record")
        payload = {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]}
        response_data = {"raw": {"choices": [{"message": {"content": "hello"}}]}, "latency_s": 0.1, "error": None}
        cache_rec.put(payload, None, response_data)
        
        # Replay mode
        cache_rep = RequestCache(tmpdir, mode="replay")
        hit = cache_rep.get(payload, None)
        assert hit is not None
        assert hit["raw"]["choices"][0]["message"]["content"] == "hello"
        
        # Cache miss in replay mode raises CacheMiss
        missing_payload = {"model": "test-model", "messages": [{"role": "user", "content": "other"}]}
        with pytest.raises(CacheMiss):
            cache_rep.get(missing_payload, None)

# 4. Sandbox Isolation Tests
def test_sandbox_valid_code():
    code = "print(42)"
    res = run_in_sandbox(code)
    assert res.get("result") == 42

def test_sandbox_syntax_error():
    code = "def broken(:"
    res = run_in_sandbox(code)
    assert "error" in res

def test_sandbox_timeout():
    code = "while True: pass"
    res = run_in_sandbox(code, timeout_s=1.0)
    assert res.get("error") == "timeout"

# 5. YAML Loader Validation Tests
def test_load_builtin_and_example_pack():
    builtins = get_builtin_scenarios()
    assert len(builtins) == 9
    
    pack_path = Path(__file__).parent.parent / "scenario_packs" / "example_pack.yaml"
    if pack_path.exists():
        loaded = load_yaml_pack(str(pack_path))
        assert len(loaded) >= 1
        assert loaded[0].vector == "empty_result"

def test_load_yaml_pack_validation_failure():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("name: test\nvector: empty_result\n") # missing task_prompt, tools, etc.
        fname = f.name
        
    try:
        with pytest.raises(ValueError):
            load_yaml_pack(fname)
    finally:
        os.remove(fname)

# 6. Synthesizer and Manifest Tests
def test_routing_manifest_mandatory_keys():
    mock_chaos = [
        EpisodeResult("schema_drift", 0, True, None, 2, 0.2, "ok"),
        EpisodeResult("prompt_injection", 0, True, None, 2, 0.2, "ok")
    ]
    mock_domains = {
        "code_generation": DomainResult("code_generation", True, 90.0, 5, 5, 100.0, 56.5, 100.0, False, {}, 0.1, []),
        "structured_data": DomainResult("structured_data", True, 85.0, 5, 4, 80.0, 37.5, 96.4, True, {}, 0.1, []),
        "algorithmic_logic": DomainResult("algorithmic_logic", True, 80.0, 5, 4, 80.0, 37.5, 96.4, True, {}, 0.1, []),
        "vision_processing": DomainResult("vision_processing", False, None, 0, 0, None, None, None, None, {}, None, [], "Disabled")
    }
    
    manifest = build_routing_manifest("test_model", mock_chaos, mock_domains, seed=42, trials=1)
    
    mandatory_keys = [
        "model_target", "overall_resilience", "overall_resilience_weighted",
        "overall_resilience_lcb", "competency_scores", "competency_ci",
        "tiers", "production_readiness", "production_readiness_score",
        "recommended_route", "routing_constraints", "silent_corruption_rate",
        "failure_taxonomy", "per_vector_resilience", "efficiency",
        "capability_probe", "seed", "trials", "timestamp", "versions"
    ]
    for key in mandatory_keys:
        assert key in manifest, f"Missing mandatory key: {key}"
        
    # Check that N/A domain score is None
    assert manifest["competency_scores"]["vision_processing"] is None
    assert manifest["tiers"]["vision_processing"] == "N/A"
    assert manifest["production_readiness"]["vision_processing"] is False

def test_routing_constraints_derivation():
    fail_tax = {
        FailureLabel.LOOP.value: 2,
        FailureLabel.INJECTION_FOLLOWED.value: 1
    }
    tiers = {"code_generation": "SUPERVISED"}
    constraints = derive_routing_constraints(fail_tax, tiers, 80.0)
    assert any("retry ceiling" in c for c in constraints)
    assert any("destructive tools" in c for c in constraints)

def test_radar_and_badge_generation():
    scores = {"code_generation": 90.0, "structured_data": 80.0, "algorithmic_logic": 70.0, "vision_processing": None}
    tiers = {"code_generation": "AUTONOMOUS", "structured_data": "SUPERVISED", "algorithmic_logic": "SUPERVISED", "vision_processing": "N/A"}
    svg_radar = generate_radar_chart_svg(scores, tiers)
    assert "<svg" in svg_radar
    
    svg_badge = generate_svg_badge("AUTONOMOUS", 95.0)
    assert "<svg" in svg_badge
    assert "AUTONOMOUS" in svg_badge
