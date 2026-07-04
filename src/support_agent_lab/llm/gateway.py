from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, Field

from support_agent_lab.config import Settings, get_settings
from support_agent_lab.models import LLMCallTrace


_RETRYABLE_STATUS_CODES = {408, 409, 429}
_RETRYABLE_ERROR_NAME_PARTS = (
    "timeout",
    "ratelimit",
    "rate_limit",
    "apiconnection",
    "connection",
    "internalserver",
    "serviceunavailable",
)


@dataclass
class _CircuitState:
    failure_count: int = 0
    opened_at: float | None = None


class LLMCircuitOpen(RuntimeError):
    pass


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

    async def health_check(self) -> None:
        ...


class ProductionConfigError(RuntimeError):
    pass


@dataclass
class LocalDeterministicProvider:
    """Local-only provider used by tests and onboarding.

    Production mode refuses to use this provider. It exists so regression tests
    can stay deterministic while the production wiring uses real model calls.
    """

    provider: str = "local_deterministic"
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

    async def health_check(self) -> None:
        return None


@dataclass
class OpenAIResponsesProvider:
    api_key: str
    model: str
    timeout_ms: int = 15_000
    provider: str = "openai"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        from openai import AsyncOpenAI

        started = perf_counter()
        client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout_ms / 1000)
        input_text = "\n\n".join(
            [
                f"Task: {request.task}",
                f"System context: {request.system_context}",
                f"User context: {request.user_context}",
                f"Grounded draft from tools and retrieval: {request.fallback_content}",
            ]
        )
        response = await client.responses.create(
            model=self.model,
            instructions=(
                "You are a production customer-support agent. Use only the provided "
                "tool and retrieval context. Do not invent order, invoice, shipment, "
                "refund, or account-security facts."
            ),
            input=input_text,
        )
        content = response.output_text
        trace = LLMCallTrace(
            provider=self.provider,
            model=self.model,
            prompt_version=request.prompt_version,
            latency_ms=int((perf_counter() - started) * 1000),
            input_tokens=estimate_tokens(input_text),
            output_tokens=estimate_tokens(content),
            cost_usd=0.0,
            fallback_used=False,
        )
        return LLMResponse(content=content, trace=trace)

    async def health_check(self) -> None:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout_ms / 1000)
        await client.models.retrieve(self.model)


@dataclass
class LLMGateway:
    provider: LLMProvider
    timeout_ms: int = 15_000
    retry_attempts: int = 2
    retry_backoff_ms: int = 250
    circuit_failure_threshold: int = 5
    circuit_reset_seconds: int = 30
    clock: Callable[[], float] | None = None
    _circuit: _CircuitState = field(default_factory=_CircuitState, init=False)

    def __post_init__(self) -> None:
        self.retry_attempts = max(1, self.retry_attempts)
        self.retry_backoff_ms = max(0, self.retry_backoff_ms)
        self.circuit_failure_threshold = max(1, self.circuit_failure_threshold)
        self.circuit_reset_seconds = max(0, self.circuit_reset_seconds)
        self._clock = self.clock or time.monotonic

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self._raise_if_circuit_open()
                response = await asyncio.wait_for(self.provider.generate(request), timeout=self.timeout_ms / 1000)
            except Exception as exc:
                last_error = exc
                retryable = _is_retryable_llm_error(exc)
                self._record_failure(retryable=retryable)
                if not self._should_retry(retryable=retryable, attempt=attempt):
                    return self._fallback_response(request, started, exc)
                await self._sleep_before_retry(attempt)
                continue
            self._record_success()
            return response
        return self._fallback_response(request, started, last_error or RuntimeError("LLM provider failed"))

    async def health_check(self) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self._raise_if_circuit_open()
                await asyncio.wait_for(self.provider.health_check(), timeout=self.timeout_ms / 1000)
            except Exception as exc:
                last_error = exc
                retryable = _is_retryable_llm_error(exc)
                self._record_failure(retryable=retryable)
                if not self._should_retry(retryable=retryable, attempt=attempt):
                    raise RuntimeError(f"LLM provider readiness check failed: {type(exc).__name__}") from exc
                await self._sleep_before_retry(attempt)
                continue
            self._record_success()
            return None
        if last_error:
            raise RuntimeError(f"LLM provider readiness check failed: {type(last_error).__name__}") from last_error

    def circuit_status(self) -> dict[str, object]:
        opened_seconds_ago: float | None = None
        if self._circuit.opened_at is not None:
            opened_seconds_ago = round(max(0.0, self._clock() - self._circuit.opened_at), 3)
        return {
            "state": self._circuit_state(),
            "failure_count": self._circuit.failure_count,
            "failure_threshold": self.circuit_failure_threshold,
            "reset_seconds": self.circuit_reset_seconds,
            "opened_seconds_ago": opened_seconds_ago,
            "retry_attempts": self.retry_attempts,
            "timeout_ms": self.timeout_ms,
        }

    def _fallback_response(self, request: LLMRequest, started: float, exc: Exception) -> LLMResponse:
        content = request.fallback_content
        trace = LLMCallTrace(
            provider=self.provider.provider,
            model=self.provider.model,
            prompt_version=request.prompt_version,
            latency_ms=int((perf_counter() - started) * 1000),
            input_tokens=estimate_tokens(
                " ".join(
                    [
                        request.task,
                        str(request.system_context),
                        str(request.user_context),
                        request.fallback_content,
                    ]
                )
            ),
            output_tokens=estimate_tokens(content),
            cost_usd=0.0,
            fallback_used=True,
            error_type=type(exc).__name__,
        )
        return LLMResponse(content=content, trace=trace)

    def _should_retry(self, *, retryable: bool, attempt: int) -> bool:
        if not retryable or attempt >= self.retry_attempts:
            return False
        return self._circuit_state() != "open"

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_ms <= 0:
            return
        backoff_seconds = (self.retry_backoff_ms / 1000) * (2 ** (attempt - 1))
        await asyncio.sleep(backoff_seconds)

    def _raise_if_circuit_open(self) -> None:
        if self._circuit_state() == "open":
            raise LLMCircuitOpen("LLM provider circuit is open")

    def _record_success(self) -> None:
        self._circuit.failure_count = 0
        self._circuit.opened_at = None

    def _record_failure(self, *, retryable: bool) -> None:
        if not retryable:
            return
        self._circuit.failure_count += 1
        if self._circuit.failure_count >= self.circuit_failure_threshold:
            self._circuit.opened_at = self._clock()

    def _circuit_state(self) -> str:
        opened_at = self._circuit.opened_at
        if opened_at is None:
            return "closed"
        if self._clock() - opened_at >= self.circuit_reset_seconds:
            return "half_open"
        return "open"


def create_default_llm_gateway() -> LLMGateway:
    return create_llm_gateway(get_settings())


def create_llm_gateway(settings: Settings) -> LLMGateway:
    if settings.app_model_provider == "openai":
        if not settings.openai_api_key:
            raise ProductionConfigError("OPENAI_API_KEY is required when APP_MODEL_PROVIDER=openai")
        return LLMGateway(
            provider=OpenAIResponsesProvider(
                api_key=settings.openai_api_key,
                model=settings.app_openai_model,
                timeout_ms=settings.app_llm_timeout_ms,
            ),
            timeout_ms=settings.app_llm_timeout_ms,
            retry_attempts=settings.app_llm_retry_attempts,
            retry_backoff_ms=settings.app_llm_retry_backoff_ms,
            circuit_failure_threshold=settings.app_llm_circuit_failure_threshold,
            circuit_reset_seconds=settings.app_llm_circuit_reset_seconds,
        )
    if settings.is_production:
        raise ProductionConfigError("Production mode requires APP_MODEL_PROVIDER=openai")
    if settings.app_model_provider == "local_deterministic":
        return LLMGateway(
            provider=LocalDeterministicProvider(),
            timeout_ms=settings.app_llm_timeout_ms,
            retry_attempts=settings.app_llm_retry_attempts,
            retry_backoff_ms=settings.app_llm_retry_backoff_ms,
            circuit_failure_threshold=settings.app_llm_circuit_failure_threshold,
            circuit_reset_seconds=settings.app_llm_circuit_reset_seconds,
        )
    raise ProductionConfigError(f"Unknown APP_MODEL_PROVIDER: {settings.app_model_provider}")


def estimate_tokens(text: str) -> int:
    # Good enough for cost trend demos; real gateways should use model tokenizers.
    return max(1, len(text) // 4)


def _is_retryable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, LLMCircuitOpen):
        return False
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    status_code = _status_code(exc)
    if status_code is not None:
        return status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code <= 599
    error_name = type(exc).__name__.lower()
    return any(part in error_name for part in _RETRYABLE_ERROR_NAME_PARTS)


def _status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    return None
