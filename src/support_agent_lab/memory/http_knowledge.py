from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from support_agent_lab.models import RetrievalContext, RetrievalHit, RetrievalTrace


_RETRYABLE_STATUS_CODES = {429}


@dataclass
class _CircuitState:
    failure_count: int = 0
    opened_at: float | None = None


class _KnowledgeHTTPError(Exception):
    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class HTTPKnowledgeIndex:
    """Production knowledge adapter backed by an HTTP knowledge service.

    Expected endpoint:
      GET /knowledge/search?query=<text>&limit=<n>

    Response can be either {"hits": [...]} or a bare list of hit objects.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_ms: int = 5000,
        retry_attempts: int = 2,
        retry_backoff_ms: int = 100,
        circuit_failure_threshold: int = 5,
        circuit_reset_seconds: int = 30,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout_ms / 1000
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_ms = max(0, retry_backoff_ms)
        self.circuit_failure_threshold = max(1, circuit_failure_threshold)
        self.circuit_reset_seconds = max(0, circuit_reset_seconds)
        self.transport = transport
        self._clock = clock or time.monotonic
        self._circuit = _CircuitState()

    async def search(
        self,
        query: str,
        limit: int = 4,
        context: RetrievalContext | None = None,
    ) -> RetrievalTrace:
        headers = self._headers(context)
        try:
            payload = await self._request(
                "/knowledge/search",
                headers=headers,
                params={"query": query, "limit": limit},
                parse_json=True,
            )
        except _KnowledgeHTTPError as exc:
            return self._empty_trace(query, exc.reason)
        try:
            if payload is None:
                return self._empty_trace(query, "knowledge_bad_payload")
            raw_hits = payload.get("hits", payload) if isinstance(payload, dict) else payload
            hits = [self._parse_hit(item) for item in raw_hits[:limit]]
        except (KeyError, TypeError, ValueError):
            return self._empty_trace(query, "knowledge_bad_payload")
        dropped_candidates = self._safe_strings(payload, "dropped_candidates", fallback=[])
        if not dropped_candidates:
            dropped_candidates = [
                str(item.get("chunk_id") or item.get("id") or index)
                for index, item in enumerate(raw_hits[limit:], start=limit)
                if isinstance(item, dict)
            ]
        return RetrievalTrace(
            query=query,
            rewritten_queries=self._safe_strings(payload, "rewritten_queries", fallback=[query]),
            selected_sources=[hit.source_uri for hit in hits],
            candidates_by_stage=self._safe_stage_counts(
                payload,
                fallback={"http": len(raw_hits), "selected": len(hits)},
            ),
            selected_context=hits,
            dropped_candidates=dropped_candidates,
        )

    def _headers(self, context: RetrievalContext | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if context:
            headers.update(
                {
                    "X-Tenant-Id": _header_value(context.tenant_id),
                    "X-Actor-User-Id": _header_value(context.actor_user_id),
                    "X-Actor-Roles": _header_csv(context.actor_roles),
                    "X-Actor-Scopes": _header_csv(context.actor_scopes),
                    "X-Request-Id": _header_value(context.request_id),
                    "X-Trace-Id": _header_value(context.trace_id),
                }
            )
            if context.parent_trace_id:
                headers["X-Parent-Trace-Id"] = _header_value(context.parent_trace_id)
        return headers

    async def health_check(self) -> None:
        try:
            await self._request("/health", headers=self._headers(), parse_json=False)
        except _KnowledgeHTTPError as exc:
            raise RuntimeError(f"Knowledge API readiness check failed: {exc.reason}") from exc

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
        }

    async def _request(
        self,
        path: str,
        *,
        headers: dict[str, str],
        params: dict | None = None,
        parse_json: bool,
    ) -> object:
        last_error: _KnowledgeHTTPError | None = None
        for attempt in range(1, self.retry_attempts + 1):
            self._raise_if_circuit_open()
            try:
                payload = await self._send_once(path, headers=headers, params=params, parse_json=parse_json)
            except _KnowledgeHTTPError as exc:
                last_error = exc
                self._record_failure(exc)
                if not self._should_retry(exc, attempt=attempt):
                    raise
                await self._sleep_before_retry(attempt)
                continue
            self._record_success()
            return payload
        if last_error:
            raise last_error
        raise _KnowledgeHTTPError("knowledge_unavailable", retryable=True)

    async def _send_once(
        self,
        path: str,
        *,
        headers: dict[str, str],
        params: dict | None,
        parse_json: bool,
    ) -> object:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=params)
                response.raise_for_status()
                if not parse_json:
                    return None
                return response.json()
        except httpx.TimeoutException as exc:
            raise _KnowledgeHTTPError("knowledge_timeout", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            retryable = status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code <= 599
            raise _KnowledgeHTTPError(f"knowledge_http_{status_code}", retryable=retryable) from exc
        except httpx.HTTPError as exc:
            raise _KnowledgeHTTPError("knowledge_unavailable", retryable=True) from exc
        except ValueError as exc:
            raise _KnowledgeHTTPError("knowledge_bad_payload", retryable=True) from exc

    def _should_retry(self, exc: _KnowledgeHTTPError, *, attempt: int) -> bool:
        if attempt >= self.retry_attempts:
            return False
        if self._circuit_state() == "open":
            return False
        return exc.retryable

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_ms <= 0:
            return
        backoff_seconds = (self.retry_backoff_ms / 1000) * (2 ** (attempt - 1))
        await asyncio.sleep(backoff_seconds)

    def _raise_if_circuit_open(self) -> None:
        if self._circuit_state() == "open":
            raise _KnowledgeHTTPError("knowledge_circuit_open", retryable=True)

    def _record_success(self) -> None:
        self._circuit.failure_count = 0
        self._circuit.opened_at = None

    def _record_failure(self, exc: _KnowledgeHTTPError) -> None:
        if not exc.retryable:
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

    def _empty_trace(self, query: str, reason: str) -> RetrievalTrace:
        return RetrievalTrace(
            query=query,
            rewritten_queries=[query],
            selected_sources=[],
            candidates_by_stage={reason: 1, "selected": 0},
            selected_context=[],
            dropped_candidates=[reason],
        )

    def _parse_hit(self, item: dict) -> RetrievalHit:
        return RetrievalHit(
            document_id=str(item["document_id"]),
            chunk_id=str(item.get("chunk_id") or f"{item['document_id']}:0"),
            title=str(item.get("title") or item["document_id"]),
            content=str(item["content"]),
            score=float(item.get("score", 1.0)),
            source_uri=str(item.get("source_uri") or item.get("url") or ""),
            metadata=dict(item.get("metadata") or {}),
        )

    def _safe_strings(self, payload: object, key: str, *, fallback: list[str]) -> list[str]:
        if not isinstance(payload, dict):
            return fallback
        value = payload.get(key)
        if not isinstance(value, list):
            return fallback
        safe = [str(item) for item in value if isinstance(item, str) and item]
        return safe or fallback

    def _safe_stage_counts(self, payload: object, *, fallback: dict[str, int]) -> dict[str, int]:
        if not isinstance(payload, dict):
            return fallback
        value = payload.get("candidates_by_stage")
        if not isinstance(value, dict):
            return fallback
        safe: dict[str, int] = {}
        for key, count in value.items():
            if isinstance(key, str) and type(count) is int and count >= 0:
                safe[key] = count
        return safe or fallback


def _header_value(value: str) -> str:
    return " ".join(value.split())


def _header_csv(values: list[str]) -> str:
    return ",".join(_header_value(value) for value in values if value.strip())
