import asyncio

import pytest

from support_agent_lab.llm.gateway import LLMGateway, LLMRequest, LLMResponse, create_default_llm_gateway
from support_agent_lab.models import LLMCallTrace


class SlowProvider:
    provider = "slow"
    model = "slow-model"

    async def generate(self, request: LLMRequest):
        await asyncio.sleep(0.05)
        raise AssertionError("timeout should cancel slow provider")


class _StatusCodeError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class FlakyProvider:
    provider = "flaky"
    model = "flaky-model"

    def __init__(self, failures_before_success: int = 1) -> None:
        self.failures_before_success = failures_before_success
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise _StatusCodeError(500)
        return _llm_response("Model answer after retry.")

    async def health_check(self) -> None:
        return None


class AlwaysFailProvider:
    provider = "failing"
    model = "failing-model"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        raise _StatusCodeError(500)

    async def health_check(self) -> None:
        self.calls += 1
        raise _StatusCodeError(500)


@pytest.mark.asyncio
async def test_local_deterministic_gateway_records_cost_latency_and_tokens():
    gateway = create_default_llm_gateway()

    response = await gateway.generate(
        LLMRequest(
            task="Answer a support question",
            fallback_content="Use the deterministic support answer.",
            system_context={"intent": "refund_or_return"},
        )
    )

    assert response.content == "Use the deterministic support answer."
    assert response.trace.provider == "local_deterministic"
    assert response.trace.model == "deterministic-support-agent"
    assert response.trace.prompt_version == "support_answer_v1"
    assert response.trace.input_tokens > 0
    assert response.trace.output_tokens > 0
    assert response.trace.cost_usd == 0.0
    assert response.trace.fallback_used is True


@pytest.mark.asyncio
async def test_agent_run_records_llm_call_trace():
    from support_agent_lab.bootstrap import create_container

    container = create_container()
    response = await container.orchestrator.handle_message(
        conversation_id="conv_llm_trace",
        user_id="user_demo",
        text="\u6211\u8ba2\u5355 A1001 \u7684\u8033\u673a\u574f\u4e86\uff0c\u80fd\u9000\u5417\uff1f",
    )

    assert response.trace.llm_calls
    assert response.trace.llm_calls[0].provider == "local_deterministic"
    assert response.trace.llm_calls[0].prompt_version == "support_answer_v1"
    assert response.trace.llm_calls[0].output_tokens > 0


@pytest.mark.asyncio
async def test_gateway_falls_back_on_timeout_with_trace():
    gateway = LLMGateway(provider=SlowProvider(), timeout_ms=1, retry_attempts=1)

    response = await gateway.generate(
        LLMRequest(
            task="Answer a support question",
            fallback_content="Use the grounded draft when the provider times out.",
        )
    )

    assert response.content == "Use the grounded draft when the provider times out."
    assert response.trace.provider == "slow"
    assert response.trace.fallback_used is True
    assert response.trace.error_type == "TimeoutError"


@pytest.mark.asyncio
async def test_gateway_retries_transient_error_before_returning_model_answer():
    provider = FlakyProvider()
    gateway = LLMGateway(provider=provider, retry_attempts=2, retry_backoff_ms=0)

    response = await gateway.generate(
        LLMRequest(
            task="Answer a support question",
            fallback_content="Use the grounded draft only if model fails.",
        )
    )

    assert response.content == "Model answer after retry."
    assert response.trace.fallback_used is False
    assert provider.calls == 2
    assert gateway.circuit_status()["state"] == "closed"


@pytest.mark.asyncio
async def test_gateway_opens_circuit_and_falls_back_fast_after_retryable_failures():
    provider = AlwaysFailProvider()
    gateway = LLMGateway(
        provider=provider,
        retry_attempts=1,
        circuit_failure_threshold=1,
        circuit_reset_seconds=60,
    )
    request = LLMRequest(task="Answer", fallback_content="Grounded draft.")

    first = await gateway.generate(request)
    second = await gateway.generate(request)

    assert first.content == "Grounded draft."
    assert first.trace.error_type == "_StatusCodeError"
    assert second.content == "Grounded draft."
    assert second.trace.error_type == "LLMCircuitOpen"
    assert provider.calls == 1
    assert gateway.circuit_status()["state"] == "open"


@pytest.mark.asyncio
async def test_gateway_half_open_success_closes_circuit():
    now = 0.0

    def clock() -> float:
        return now

    provider = FlakyProvider(failures_before_success=1)
    gateway = LLMGateway(
        provider=provider,
        retry_attempts=1,
        circuit_failure_threshold=1,
        circuit_reset_seconds=10,
        clock=clock,
    )
    request = LLMRequest(task="Answer", fallback_content="Grounded draft.")

    failed = await gateway.generate(request)
    assert failed.trace.fallback_used is True
    assert gateway.circuit_status()["state"] == "open"

    now = 11.0
    recovered = await gateway.generate(request)

    assert recovered.content == "Model answer after retry."
    assert recovered.trace.fallback_used is False
    assert provider.calls == 2
    assert gateway.circuit_status()["state"] == "closed"
    assert gateway.circuit_status()["failure_count"] == 0


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        trace=LLMCallTrace(
            provider="flaky",
            model="flaky-model",
            prompt_version="support_answer_v1",
            latency_ms=1,
            input_tokens=1,
            output_tokens=1,
            fallback_used=False,
        ),
    )
