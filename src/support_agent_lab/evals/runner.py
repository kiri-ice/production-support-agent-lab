from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from support_agent_lab.bootstrap import create_container
from support_agent_lab.models import EvalCase, EvalCaseResult, EvalReport, ToolStatus, new_id


def load_cases(path: str | Path) -> list[EvalCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalCase.model_validate(item) for item in data]


async def run_cases(cases: list[EvalCase], orchestrator) -> EvalReport:
    results: list[EvalCaseResult] = []
    for case in cases:
        conversation_id = new_id("eval_conv")
        response = None
        for turn in case.turns:
            if turn["role"] != "user":
                continue
            response = await orchestrator.handle_message(
                conversation_id=conversation_id,
                user_id=case.user_id,
                text=turn["content"],
            )
        assert response is not None
        observed_tools = [
            tool.name for tool in response.trace.tool_results if tool.status == ToolStatus.success
        ]
        observed_error_codes = [
            tool.error_code for tool in response.trace.tool_results if tool.error_code
        ]
        failures = _check_case(case, response, observed_tools, observed_error_codes)
        score = max(0.0, 1.0 - 0.2 * len(failures))
        results.append(
            EvalCaseResult(
                case_id=case.case_id,
                passed=not failures,
                score=score,
                failures=failures,
                observed_intent=response.trace.intent.primary,
                observed_tools=observed_tools,
                observed_error_codes=observed_error_codes,
                answer=response.message.content,
            )
        )
    passed = sum(1 for result in results if result.passed)
    return EvalReport(total=len(results), passed=passed, score=passed / max(len(results), 1), results=results)


def _check_case(
    case: EvalCase,
    response,
    observed_tools: list[str],
    observed_error_codes: list[str],
) -> list[str]:
    failures: list[str] = []
    expected = case.expected
    answer = response.message.content
    if expected.intent and response.trace.intent.primary != expected.intent:
        failures.append(f"intent expected {expected.intent.value}, got {response.trace.intent.primary.value}")
    for tool in expected.required_tools:
        if tool not in observed_tools:
            failures.append(f"required tool not called: {tool}")
    for error_code in expected.required_error_codes:
        if error_code not in observed_error_codes:
            failures.append(f"required error code not observed: {error_code}")
    for text in expected.must_include:
        if text not in answer:
            failures.append(f"answer missing: {text}")
    for text in expected.must_not_include:
        if text in answer:
            failures.append(f"answer included forbidden text: {text}")
    if expected.escalation is not None and response.handoff_required != expected.escalation:
        failures.append(f"escalation expected {expected.escalation}, got {response.handoff_required}")
    selected_doc_ids = [hit.document_id for hit in response.citations]
    for doc_id in expected.policy_refs:
        if doc_id not in selected_doc_ids:
            failures.append(f"missing citation doc: {doc_id}")
    return failures


async def async_main(path: str) -> EvalReport:
    container = create_container()
    cases = load_cases(path)
    report = await run_cases(cases, container.orchestrator)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline agent evals.")
    parser.add_argument("path", nargs="?", default="examples/evals/golden_core.json")
    args = parser.parse_args()
    asyncio.run(async_main(args.path))


if __name__ == "__main__":
    main()
