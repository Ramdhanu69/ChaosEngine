import time
from typing import Any
from .scoring import DomainResult, ItemResult, wilson_interval
from .domains.code import run_domain_code
from .domains.data import run_domain_data
from .domains.logic import run_domain_logic
from .domains.vision import run_domain_vision
from .client import LLMClient
from .mocks import MockModel

def aggregate_domain(domain_name: str, items: list[ItemResult], supported: bool = True, na_reason: str | None = None) -> DomainResult:
    if not supported or not items:
        return DomainResult(
            domain=domain_name,
            supported=supported,
            score=None,
            items_evaluated=0,
            exact_passes=0,
            exact_pass_rate=None,
            wilson_lower=None,
            wilson_upper=None,
            low_confidence=None,
            failure_counts={},
            avg_latency_s=None,
            items=[],
            na_reason=na_reason or ("Unsupported" if not supported else "No items evaluated")
        )
        
    n = len(items)
    exact_passes = sum(1 for it in items if it.passed)
    pass_rate = (exact_passes / n) * 100.0
    
    # Domain score is arithmetic mean of item scores multiplied by 100
    avg_score = (sum(it.score for it in items) / n) * 100.0
    
    pt, ci_lower, ci_upper = wilson_interval(exact_passes, n)
    low_conf = (ci_upper - ci_lower) > 30.0
    
    fail_counts = {}
    for it in items:
        if it.failure_label:
            fail_counts[it.failure_label] = fail_counts.get(it.failure_label, 0) + 1
            
    avg_lat = sum(it.latency_s for it in items) / n if n > 0 else 0.0
    
    return DomainResult(
        domain=domain_name,
        supported=True,
        score=avg_score,
        items_evaluated=n,
        exact_passes=exact_passes,
        exact_pass_rate=pass_rate,
        wilson_lower=ci_lower,
        wilson_upper=ci_upper,
        low_confidence=low_conf,
        failure_counts=fail_counts,
        avg_latency_s=avg_lat,
        items=items,
        na_reason=None
    )

def run_domain_suite(
    client: Any,
    seed: int = 42,
    items_per_domain: int = 10,
    skip_vision: bool = False,
    domains_to_run: list[str] | None = None
) -> dict[str, DomainResult]:
    """
    Runs the domain competency profiling suite across:
    - code_generation
    - structured_data
    - algorithmic_logic
    - vision_processing
    """
    if domains_to_run is None:
        domains_to_run = ["code", "data", "logic", "vision"]
        
    results: dict[str, DomainResult] = {}
    
    # Check client probe capabilities
    probe_info = client.probe() if hasattr(client, "probe") else {}
    vision_supported = probe_info.get("vision", False) if not skip_vision else False
    
    # 1. Code
    if "code" in domains_to_run:
        code_items = run_domain_code(client, seed, items_per_domain)
        results["code_generation"] = aggregate_domain("code_generation", code_items, supported=True)
        
    # 2. Data
    if "data" in domains_to_run:
        data_items = run_domain_data(client, seed, items_per_domain)
        results["structured_data"] = aggregate_domain("structured_data", data_items, supported=True)
        
    # 3. Logic
    if "logic" in domains_to_run:
        logic_items = run_domain_logic(client, seed, items_per_domain)
        results["algorithmic_logic"] = aggregate_domain("algorithmic_logic", logic_items, supported=True)
        
    # 4. Vision
    if "vision" in domains_to_run:
        if skip_vision or not vision_supported:
            reason = "--no-vision requested" if skip_vision else "Model capability probe indicated no vision support"
            results["vision_processing"] = aggregate_domain("vision_processing", [], supported=False, na_reason=reason)
        else:
            vision_items = run_domain_vision(client, seed, items_per_domain, skip_vision=False)
            results["vision_processing"] = aggregate_domain("vision_processing", vision_items, supported=True)
            
    return results
