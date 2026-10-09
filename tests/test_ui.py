import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from rich.console import Console

from chaosharness.ui import render_dashboard, make_bar, format_size
from chaosharness.cli import main

@pytest.fixture
def sample_manifest():
    return {
        "model_target": "test-model-v1",
        "overall_resilience": 88.5,
        "overall_resilience_weighted": 90.0,
        "overall_resilience_lcb": 75.2,
        "silent_corruption_rate": 0.0,
        "recommended_route": "Workflow/State Orchestration Agent",
        "routing_constraints": [
            "Enforce an external retry ceiling of 3."
        ],
        "per_vector_resilience": {
            "schema_drift": 100.0,
            "tool_schema_change": 80.0,
            "rate_limit_429": 100.0,
            "retry_trap_503": 50.0,
            "malformed_payload": 100.0,
            "empty_result": 100.0,
            "phantom_tool_lure": 100.0,
            "prompt_injection": 100.0,
            "timeout": 100.0
        },
        "failure_taxonomy": {
            "LOOP": 2,
            "BAD_FORMAT": 1
        },
        "competency_scores": {
            "code_generation": 95.0,
            "structured_data": 85.0,
            "algorithmic_logic": 90.0,
            "vision_processing": None
        },
        "competency_ci": {
            "code_generation": [80.0, 100.0],
            "structured_data": [70.0, 95.0],
            "algorithmic_logic": [75.0, 98.0],
            "vision_processing": None
        },
        "tiers": {
            "code_generation": "AUTONOMOUS",
            "structured_data": "SUPERVISED",
            "algorithmic_logic": "AUTONOMOUS",
            "vision_processing": "N/A"
        },
        "production_readiness": {
            "code_generation": True,
            "structured_data": True,
            "algorithmic_logic": True,
            "vision_processing": False
        },
        "provenance": {
            "mode": "live",
            "synthetic": False,
            "endpoint": "http://localhost:11434",
            "seed": 42,
            "trials": 5,
            "items": 10,
            "ollama_version": "0.1.30",
            "model_digest": "a1b2c3d4e5f6",
            "platform": "win32"
        }
    }

def test_render_dashboard_rich_console(tmp_path, sample_manifest):
    console = Console(record=True, width=100)
    render_dashboard(
        manifest=sample_manifest,
        results_summary=[],
        provenance=sample_manifest["provenance"],
        out_dir=tmp_path,
        console=console
    )
    output = console.export_text()

    assert "CHAOSHARNESS" in output
    assert "Engine 1" in output
    assert "Engine 2" in output
    assert "Primary Failure Taxonomy" in output
    assert "Verdict & Routing Contract" in output
    assert "Generated Artifacts" in output
    assert "test-model-v1" in output
    assert "AUTONOMOUS" in output

def test_render_dashboard_fallback_plain_console(tmp_path, sample_manifest, capsys):
    render_dashboard(
        manifest=sample_manifest,
        results_summary=[],
        provenance=sample_manifest["provenance"],
        out_dir=tmp_path,
        console=None
    )
    captured = capsys.readouterr()

    assert "ChaosHarness Scorecard: test-model-v1" in captured.out
    assert "Overall Resilience: 88.5%" in captured.out
    assert "Recommended Route: Workflow/State Orchestration Agent" in captured.out
    assert "LOOP: 2" in captured.out

def test_render_dashboard_synthetic_demo_watermark(tmp_path, sample_manifest):
    sample_manifest["provenance"]["synthetic"] = True
    console = Console(record=True, width=100)
    render_dashboard(
        manifest=sample_manifest,
        results_summary=[],
        provenance=sample_manifest["provenance"],
        out_dir=tmp_path,
        console=console
    )
    output = console.export_text()

    assert "SYNTHETIC DEMO DATA — NOT A MODEL RESULT" in output
    assert "SYNTHETIC DEMO" in output

def test_cli_json_flag(tmp_path, capsys):
    with patch.object(sys, "argv", [
        "chaosharness", "run",
        "--model", "test-json-model",
        "--mock", "good",
        "--quick",
        "--no-vision",
        "--json",
        "--out", str(tmp_path / "json_out")
    ]):
        ret = main()
        assert ret == 0

    captured = capsys.readouterr()
    # Output must be parseable JSON
    data = json.loads(captured.out)
    assert data["model_target"] == "test-json-model"
    assert data["overall_resilience"] == 100.0

def test_cli_no_color_flag(tmp_path, capsys):
    with patch.object(sys, "argv", [
        "chaosharness", "run",
        "--model", "test-nocolor-model",
        "--mock", "good",
        "--quick",
        "--no-vision",
        "--no-color",
        "--out", str(tmp_path / "nocolor_out")
    ]):
        ret = main()
        assert ret == 0

    captured = capsys.readouterr()
    assert "ChaosHarness Scorecard: test-nocolor-model" in captured.out
    assert "\033[" not in captured.out

def test_make_bar_and_format_size():
    bar1 = make_bar(100.0, 10, is_unicode=True)
    assert bar1 == "██████████"
    bar2 = make_bar(50.0, 10, is_unicode=False)
    assert bar2 == "#####-----"
    
    assert format_size(500) == "500 B"
    assert format_size(1500) == "1.5 KB"
    assert format_size(2 * 1024 * 1024) == "2.0 MB"
