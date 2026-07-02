import pytest

from support_agent_lab.llm.gateway import LLMRequest, create_default_llm_gateway


@pytest.mark.asyncio
async def test_mock_llm_gateway_records_cost_latency_and_tokens():
    gateway = create_default_llm_gateway()

    response = await gateway.generate(
        LLMRequest(
            task="Answer a support question",
            fallback_content="Use the deterministic support answer.",
            system_context={"intent": "refund_or_return"},
        )
    )

    assert response.content == "Use the deterministic support answer."
    assert response.trace.provider == "mock"
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
    assert response.trace.llm_calls[0].provider == "mock"
    assert response.trace.llm_calls[0].prompt_version == "support_answer_v1"
    assert response.trace.llm_calls[0].output_tokens > 0

