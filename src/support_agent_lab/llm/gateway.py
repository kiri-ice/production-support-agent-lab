from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, Field

from support_agent_lab.models import LLMCallTrace


class LLMRequest(BaseModel):
    prompt_version: str = "support_answer_v1"
    task: str
    fallback_content: str
    system_context: dict = Field(default_factory=dict)
    user_context: dict = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    trace: LLMCallTrace


class LLMProvider(Protocol):
    provider: str
    model: str

    async def generate(self, request: LLMRequest) -> LLMResponse:
        ...


@dataclass
class MockLLMProvider:
    """Deterministic provider used by tests and local onboarding.

    It preserves the production boundary without requiring an API key. Swap this
    provider for a real model client in production while keeping the gateway API.
    """

    provider: str = "mock"
    model: str = "deterministic-support-agent"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = perf_counter()
        input_tokens = estimate_tokens(
            " ".join(
                [
                    request.task,
                    str(request.system_context),
                    str(request.user_context),
                ]
            )
        )
        output_tokens = estimate_tokens(request.fallback_content)
        trace = LLMCallTrace(
            provider=self.provider,
            model=self.model,
            prompt_version=request.prompt_version,
            latency_ms=int((perf_counter() - started) * 1000),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            fallback_used=True,
        )
        return LLMResponse(content=request.fallback_content, trace=trace)


@dataclass
class LLMGateway:
    provider: LLMProvider
    timeout_ms: int = 15_000

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return await self.provider.generate(request)


def create_default_llm_gateway() -> LLMGateway:
    return LLMGateway(provider=MockLLMProvider())


def estimate_tokens(text: str) -> int:
    # Good enough for cost trend demos; real gateways should use model tokenizers.
    return max(1, len(text) // 4)

