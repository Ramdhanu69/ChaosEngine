import os
import re
import pathlib
import pytest

from chaosharness.synthesizer import build_html_report, generate_report
from chaosharness.tools import ToolExecutor
from chaosharness.domains.sandbox import run_in_sandbox
from chaosharness.scoring import DomainResult

def test_html_report_xss_escaping():
    malicious_manifest = {
        "model_target": "<script>alert('XSS_TARGET')</script>",
        "recommended_route": "<img src=x onerror=alert('XSS_ROUTE')>",
        "timestamp": "2026-01-01T00:00:00Z",
        "overall_resilience": 85.0,
        "overall_resilience_weighted": 85.0,
        "overall_resilience_lcb": 75.0,
        "silent_corruption_rate": 0.0,
        "competency_scores": {
            "code_generation": 90.0,
            "structured_data": 80.0,
            "algorithmic_logic": 70.0,
            "vision_processing": None
        },
        "competency_ci": {
            "code_generation": [75.0, 95.0],
            "structured_data": [65.0, 88.0],
            "algorithmic_logic": [55.0, 82.0],
            "vision_processing": None
        },
        "tiers": {
            "code_generation": "AUTONOMOUS",
            "structured_data": "SUPERVISED",
            "algorithmic_logic": "SUPERVISED",
            "vision_processing": "N/A"
        },
        "production_readiness": {
            "code_generation": True,
            "structured_data": True,
            "algorithmic_logic": True,
            "vision_processing": False
        },
        "per_vector_resilience": {
            "<vector_tag>": 100.0
        },
        "failure_taxonomy": {
            "<bad_key>": 2
        },
        "routing_constraints": [
            "<iframe src='evil.com'></iframe>"
        ]
    }

    html = build_html_report(malicious_manifest, [], {})

    # Ensure unescaped tags are NOT present
    assert "<script>alert('XSS_TARGET')</script>" not in html
    assert "<img src=x onerror=alert('XSS_ROUTE')>" not in html
    assert "<iframe src='evil.com'></iframe>" not in html
    assert "<vector_tag>" not in html

    # Ensure escaped entities ARE present
    assert "&lt;script&gt;alert(&#x27;XSS_TARGET&#x27;)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(&#x27;XSS_ROUTE&#x27;)&gt;" in html
    assert "&lt;iframe src=&#x27;evil.com&#x27;&gt;&lt;/iframe&gt;" in html
    assert "&lt;vector_tag&gt;" in html

def test_honeypot_tool_execution_safety():
    tools = ToolExecutor(seed=42)
    assert tools.honeypot_called is False
    res = tools.execute("delete_all_records", {})
    assert res == {"status": "deleted"}
    assert tools.honeypot_called is True

def test_sandbox_network_blocking():
    code_trying_network = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print(1)
"""
    res = run_in_sandbox(code_trying_network)
    # The sandbox stubs socket.socket to raise PermissionError
    assert "error" in res
    assert "Network blocked" in res.get("output", "") or "PermissionError" in res.get("output", "") or res.get("error") == "execution_failed"

def test_repository_secrets_hygiene():
    """
    Scans the repository source files for accidental secrets, private keys, or API tokens.
    """
    repo_root = pathlib.Path(__file__).parent.parent
    patterns = [
        (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI API Key"),
        (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub Personal Access Token"),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
        (re.compile(r"-----BEGIN PRIVATE KEY-----"), "Private Key PEM"),
        (re.compile(r"-----BEGIN RSA PRIVATE KEY-----"), "RSA Private Key PEM"),
    ]

    scanned_extensions = {".py", ".json", ".yaml", ".yml", ".md", ".toml"}
    findings = []

    for file_path in repo_root.rglob("*"):
        if file_path.is_file() and file_path.suffix in scanned_extensions:
            # Skip pytest cache, git, and the test file itself
            if (
                ".pytest_cache" in str(file_path)
                or ".git" in str(file_path)
                or "__pycache__" in str(file_path)
                or file_path.name == "test_security_audit.py"
            ):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for pat, label in patterns:
                    matches = pat.findall(content)
                    if matches:
                        findings.append((str(file_path.relative_to(repo_root)), label))
            except Exception:
                pass

    assert len(findings) == 0, f"Found sensitive secrets in repository: {findings}"
