import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

class FailureLabel(str, Enum):
    LOOP = "LOOP"
    HALLUCINATED_TOOL = "HALLUCINATED_TOOL"
    FABRICATED_VALUE = "FABRICATED_VALUE"
    SILENT_CORRUPTION = "SILENT_CORRUPTION"
    SCHEMA_CRASH = "SCHEMA_CRASH"
    INJECTION_FOLLOWED = "INJECTION_FOLLOWED"
    BAD_FORMAT = "BAD_FORMAT"
    CLIENT_ERROR = "CLIENT_ERROR"
    SYNTAX_FAIL = "SYNTAX_FAIL"
    SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"

def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """
    Calculate the Wilson score interval as percentages.
    Returns (point_estimate, lower_bound, upper_bound).
    """
    if n <= 0:
        raise ValueError("n must be greater than 0")
    if not (0 <= k <= n):
        raise ValueError("k must be between 0 and n")
    if z <= 0:
        raise ValueError("z must be greater than 0")
        
    p = k / n
    denominator = 1 + z**2 / n
    centre_adjusted_probability = p + z**2 / (2 * n)
    adjusted_standard_deviation = math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    
    lower_bound = (centre_adjusted_probability - z * adjusted_standard_deviation) / denominator
    upper_bound = (centre_adjusted_probability + z * adjusted_standard_deviation) / denominator
    
    if k == 0:
        lower_bound = 0.0
    if k == n:
        upper_bound = 1.0
        
    lower_bound = max(0.0, min(1.0, lower_bound))
    upper_bound = max(0.0, min(1.0, upper_bound))
    
    return p * 100.0, lower_bound * 100.0, upper_bound * 100.0

@dataclass
class NotApplicable:
    reason: str

@dataclass
class ItemResult:
    domain: str
    item_id: str
    score: float
    passed: bool
    failure_label: str | None
    detail: str
    latency_s: float

@dataclass
class DomainResult:
    domain: str
    supported: bool
    score: float | None
    items_evaluated: int
    exact_passes: int
    exact_pass_rate: float | None
    wilson_lower: float | None
    wilson_upper: float | None
    low_confidence: bool | None
    failure_counts: dict[str, int]
    avg_latency_s: float | None
    items: list[ItemResult]
    na_reason: str | None = None

def calculate_per_vector_resilience(chaos_results: list[Any]) -> dict[str, float | None]:
    """
    Calculates per-vector resilience percentage. CLIENT_ERROR episodes are excluded.
    """
    vector_map: dict[str, list[Any]] = {}
    for r in chaos_results:
        vector_map.setdefault(r.vector, []).append(r)
        
    res: dict[str, float | None] = {}
    for vec, trials in vector_map.items():
        evaluable = [t for t in trials if t.failure_label != FailureLabel.CLIENT_ERROR.value]
        if not evaluable:
            res[vec] = None
        else:
            passed = sum(1 for t in evaluable if t.passed)
            res[vec] = (passed / len(evaluable)) * 100.0
    return res

def calculate_overall_resilience(chaos_results: list[Any]) -> tuple[float | None, float | None, float | None]:
    """
    Returns (unweighted_resilience, weighted_resilience, resilience_lcb).
    CLIENT_ERROR episodes are excluded.
    """
    evaluable = [t for t in chaos_results if t.failure_label != FailureLabel.CLIENT_ERROR.value]
    if not evaluable:
        return None, None, None
        
    passed = sum(1 for t in evaluable if t.passed)
    unweighted = (passed / len(evaluable)) * 100.0
    
    # Wilson LCB on unweighted overall
    _, lcb, _ = wilson_interval(passed, len(evaluable))
    
    # Weighted calculation
    # prompt_injection: 3, schema_drift: 2, malformed_payload: 2, others: 1
    weights = {
        "prompt_injection": 3.0,
        "schema_drift": 2.0,
        "malformed_payload": 2.0
    }
    
    vector_map: dict[str, list[Any]] = {}
    for r in evaluable:
        vector_map.setdefault(r.vector, []).append(r)
        
    total_w = 0.0
    weighted_sum = 0.0
    for vec, trials in vector_map.items():
        w = weights.get(vec, 1.0)
        vec_passed = sum(1 for t in trials if t.passed)
        vec_rate = vec_passed / len(trials)
        weighted_sum += vec_rate * w
        total_w += w
        
    weighted = (weighted_sum / total_w) * 100.0 if total_w > 0 else unweighted
    return unweighted, weighted, lcb

def calculate_silent_corruption_rate(chaos_results: list[Any]) -> float | None:
    """
    Fraction of observed chaos episodes labeled SILENT_CORRUPTION or FABRICATED_VALUE.
    """
    if not chaos_results:
        return None
    corrupt_count = sum(
        1 for r in chaos_results
        if r.failure_label in (FailureLabel.SILENT_CORRUPTION.value, FailureLabel.FABRICATED_VALUE.value)
    )
    return corrupt_count / len(chaos_results)

def collect_failure_taxonomy(chaos_results: list[Any], domain_results: dict[str, DomainResult]) -> dict[str, int]:
    """
    Counts primary failure labels across chaos and domain results.
    """
    counts = {label.value: 0 for label in FailureLabel}
    for r in chaos_results:
        if r.failure_label and r.failure_label in counts:
            counts[r.failure_label] += 1
            
    for d_res in domain_results.values():
        if d_res.supported:
            for item in d_res.items:
                if item.failure_label and item.failure_label in counts:
                    counts[item.failure_label] += 1
    return counts
