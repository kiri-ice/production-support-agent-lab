import asyncio

import pytest

from support_agent_lab.llm.gateway import LLMGateway, LLMRequest, create_default_llm_gateway


class SlowProvider:
    provider = "slow"
    model = "slow-model"

    async def generate(self, request: LLMRequest):
        await asyncio.sleep(0.05)
        raise AssertionError("timeout should cancel slow provider")


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
    gateway = LLMGateway(provider=SlowProvider(), timeout_ms=1)

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
