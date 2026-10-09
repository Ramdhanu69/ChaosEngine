"""
ChaosHarness: Automated LLM Evaluation, Runtime-Chaos Testing, and Domain-Competency Profiling.
"""

__version__ = "0.1.0"

from .client import LLMClient, ToolCall, Response
from .agent import run_episode, Episode, Step
from .chaos import run_chaos_suite, EpisodeResult
from .profiler import run_domain_suite
from .scoring import FailureLabel, DomainResult, ItemResult, wilson_interval
from .synthesizer import generate_report

__all__ = [
    "__version__",
    "LLMClient",
    "ToolCall",
    "Response",
    "run_episode",
    "Episode",
    "Step",
    "run_chaos_suite",
    "EpisodeResult",
    "run_domain_suite",
    "FailureLabel",
    "DomainResult",
    "ItemResult",
    "wilson_interval",
    "generate_report",
]
