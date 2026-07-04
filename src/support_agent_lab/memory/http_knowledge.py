from __future__ import annotations

import httpx

from support_agent_lab.models import RetrievalContext, RetrievalHit, RetrievalTrace


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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout_ms / 1000
        self.transport = transport

    async def search(
        self,
        query: str,
        limit: int = 4,
        context: RetrievalContext | None = None,
    ) -> RetrievalTrace:
        headers = self._headers(context)
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
                transport=self.transport,
            ) as client:
                response = await client.get("/knowledge/search", params={"query": query, "limit": limit})
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            return self._empty_trace(query, "knowledge_timeout")
        except httpx.HTTPStatusError as exc:
            return self._empty_trace(query, f"knowledge_http_{exc.response.status_code}")
        except httpx.HTTPError:
            return self._empty_trace(query, "knowledge_unavailable")
        except ValueError:
            return self._empty_trace(query, "knowledge_bad_payload")
        try:
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
        return headers

    async def health_check(self) -> None:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._headers(),
                transport=self.transport,
            ) as client:
                response = await client.get("/health")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Knowledge API readiness check failed") from exc

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
