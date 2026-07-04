from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EvalSuiteRunner = Literal["agent", "monitor", "retrieval"]


@dataclass(frozen=True)
class EvalSuiteSpec:
    suite_id: str
    path: str
    runner: EvalSuiteRunner
    release_step_name: str


STAGING_EVAL_SUITES: tuple[EvalSuiteSpec, ...] = (
    EvalSuiteSpec("golden_core", "examples/evals/golden_core.json", "agent", "golden eval"),
    EvalSuiteSpec("security_regression", "examples/evals/security_regression.json", "agent", "security regression eval"),
    EvalSuiteSpec(
        "tool_failure_regression",
        "examples/evals/tool_failure_regression.json",
        "agent",
        "tool failure regression eval",
    ),
    EvalSuiteSpec(
        "memory_multiturn_regression",
        "examples/evals/memory_multiturn_regression.json",
        "agent",
        "memory multiturn regression eval",
    ),
    EvalSuiteSpec("routing_regression", "examples/evals/routing_regression.json", "agent", "routing regression eval"),
    EvalSuiteSpec("monitor_regression", "examples/evals/monitor_regression.json", "monitor", "monitor regression eval"),
    EvalSuiteSpec(
        "retrieval_challenge",
        "examples/evals/retrieval_challenge.json",
        "retrieval",
        "retrieval challenge eval",
    ),
)
