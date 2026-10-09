import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from chaosharness.cli import main, run_route, run_single_model, display_scorecard, build_parser

def test_cli_top_level_help(capsys):
    with patch.object(sys, "argv", ["chaosharness", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "ChaosHarness: LLM Evaluation" in captured.out
    assert "run" in captured.out
    assert "compare" in captured.out
    assert "selftest" in captured.out
    assert "route" in captured.out

def test_cli_no_args_shows_help(capsys):
    with patch.object(sys, "argv", ["chaosharness"]):
        ret = main()
        assert ret == 0
    captured = capsys.readouterr()
    assert "usage: chaosharness" in captured.out

def test_cli_selftest_command():
    with patch.object(sys, "argv", ["chaosharness", "selftest"]):
        ret = main()
        assert ret == 0

def test_cli_run_mock_good_e2e(tmp_path):
    out_dir = tmp_path / "mock_good_out"
    with patch.object(sys, "argv", [
        "chaosharness", "run",
        "--model", "test-mock-good",
        "--mock", "good",
        "--quick",
        "--no-vision",
        "--out", str(out_dir)
    ]):
        ret = main()
        assert ret == 0

    assert (out_dir / "results.json").exists()
    assert (out_dir / "routing_manifest.json").exists()
    assert (out_dir / "EVAL_REPORT.md").exists()
    assert (out_dir / "report.html").exists()
    assert (out_dir / "badge.svg").exists()

    with open(out_dir / "routing_manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["model_target"] == "test-mock-good"
    assert manifest["overall_resilience"] == 100.0

def test_cli_run_min_tier_passed_and_failed(tmp_path):
    # Pass case: MockGood meets AUTONOMOUS
    out_dir1 = tmp_path / "pass_tier"
    with patch.object(sys, "argv", [
        "chaosharness", "run",
        "--model", "test-good",
        "--mock", "good",
        "--quick",
        "--no-vision",
        "--min-tier", "AUTONOMOUS",
        "--out", str(out_dir1)
    ]):
        assert main() == 0

    # Fail case: MockLooping is BLOCKED, cannot meet AUTONOMOUS
    out_dir2 = tmp_path / "fail_tier"
    with patch.object(sys, "argv", [
        "chaosharness", "run",
        "--model", "test-looping",
        "--mock", "looping",
        "--quick",
        "--no-vision",
        "--min-tier", "AUTONOMOUS",
        "--out", str(out_dir2)
    ]):
        ret = main()
        assert ret == 1

def test_cli_run_unreachable_endpoint(tmp_path):
    with patch.object(sys, "argv", [
        "chaosharness", "run",
        "--model", "nonexistent-model",
        "--endpoint", "http://127.0.0.1:59999",
        "--cache", "live",
        "--quick",
        "--out", str(tmp_path / "unreach")
    ]):
        ret = main()
        # Returns 2 for unreachable endpoint
        assert ret == 2

def test_cli_compare_e2e(tmp_path, capsys):
    with patch.object(sys, "argv", [
        "chaosharness", "compare",
        "--models", "mock-a,mock-b",
        "--mock", "good",
        "--quick",
        "--no-vision"
    ]):
        ret = main()
        assert ret == 0
    captured = capsys.readouterr()
    assert "Comparison Leaderboard" in captured.out
    assert "mock-a" in captured.out
    assert "mock-b" in captured.out

def test_cli_route_subcommand(tmp_path, capsys):
    manifest_path = tmp_path / "routing_manifest.json"
    manifest_data = {
        "model_target": "test-model",
        "recommended_route": "Autonomous Code Refactoring Agent",
        "tiers": {
            "code_generation": "AUTONOMOUS",
            "vision_processing": "BLOCKED"
        },
        "competency_scores": {
            "code_generation": 95.0,
            "vision_processing": 10.0
        }
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    # 1. Valid route
    with patch.object(sys, "argv", [
        "chaosharness", "route",
        "--manifest", str(manifest_path),
        "--task", "code"
    ]):
        ret = main()
        assert ret == 0
    out1 = capsys.readouterr().out
    assert "Autonomous Code Refactoring Agent" in out1

    # 2. Blocked task
    with patch.object(sys, "argv", [
        "chaosharness", "route",
        "--manifest", str(manifest_path),
        "--task", "vision"
    ]):
        ret = main()
        assert ret == 0
    out2 = capsys.readouterr().out
    assert "No eligible route for task 'vision'" in out2

    # 3. Missing manifest file
    ret_missing = run_route(str(tmp_path / "missing.json"), "code")
    assert ret_missing == 1

    # 4. Invalid task name
    ret_invalid = run_route(str(manifest_path), "unsupported_task")
    assert ret_invalid == 1

def test_cli_keyboard_interrupt_preserves_partial_results(tmp_path):
    parser = build_parser()
    args = parser.parse_args([
        "run",
        "--model", "test-interrupt",
        "--mock", "good",
        "--out", str(tmp_path / "partial")
    ])

    with patch("chaosharness.cli.run_chaos_suite", side_effect=KeyboardInterrupt):
        ret = run_single_model(args)
        assert ret == 130 # Standard SIGINT exit code

    partial_manifest = tmp_path / "partial" / "routing_manifest.json"
    assert partial_manifest.exists()
    with open(partial_manifest, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("partial") is True

def test_scorecard_fallback_display(capsys):
    manifest = {
        "model_target": "simple-model",
        "overall_resilience": 88.0,
        "overall_resilience_lcb": 75.0,
        "recommended_route": "Simple Route",
        "competency_scores": {"code_generation": 80.0},
        "tiers": {"code_generation": "AUTONOMOUS"},
        "production_readiness": {"code_generation": True}
    }
    # Test with console = None to exercise fallback branch
    with patch("chaosharness.cli.console", None):
        display_scorecard(manifest)
    captured = capsys.readouterr()
    assert "ChaosHarness Scorecard: simple-model" in captured.out
    assert "Simple Route" in captured.out


def test_cli_windows_unicode_spaces_path_support(tmp_path):
    unicode_out = tmp_path / "test dir spaces unicode 🚀"
    with patch.object(sys, "argv", [
        "chaosharness", "run",
        "--model", "test-mock-model",
        "--mock", "good",
        "--quick",
        "--no-vision",
        "--out", str(unicode_out)
    ]):
        ret = main()
        assert ret == 0
    assert (unicode_out / "routing_manifest.json").exists()
    assert (unicode_out / "results.json").exists()

