import httpx
import pytest

from support_agent_lab.memory.http_knowledge import HTTPKnowledgeIndex
from support_agent_lab.models import RetrievalContext


W3C_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


@pytest.mark.asyncio
async def test_http_knowledge_parses_hits_and_sends_auth_header():
    seen_headers = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "document_id": "invoice_policy_v1",
                        "chunk_id": "invoice_policy_v1:0",
                        "title": "Invoice policy",
                        "content": "Invoices are issued within 24 hours.",
                        "score": 0.91,
                        "source_uri": "kb://invoice_policy_v1",
                    }
                ]
            },
        )

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        api_key="knowledge-token",
        transport=httpx.MockTransport(handler),
    )

    trace = await index.search("invoice", limit=1)

    assert seen_headers["authorization"] == "Bearer knowledge-token"
    assert trace.selected_sources == ["kb://invoice_policy_v1"]
    assert trace.selected_context[0].document_id == "invoice_policy_v1"


@pytest.mark.asyncio
async def test_http_knowledge_sends_retrieval_context_headers():
    seen_headers = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"hits": []})

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        api_key="knowledge-token",
        transport=httpx.MockTransport(handler),
    )
    context = RetrievalContext(
        tenant_id="tenant_live",
        actor_user_id="user_prod",
        actor_roles=["admin", "user"],
        actor_scopes=["knowledge:diagnose", "kb:read"],
        request_id="req_knowledge_123",
        trace_id="run_knowledge_456",
        parent_trace_id="gateway_trace_789",
    )

    await index.search("invoice", limit=1, context=context)

    assert seen_headers["authorization"] == "Bearer knowledge-token"
    assert seen_headers["x-tenant-id"] == "tenant_live"
    assert seen_headers["x-actor-user-id"] == "user_prod"
    assert seen_headers["x-actor-roles"] == "admin,user"
    assert seen_headers["x-actor-scopes"] == "knowledge:diagnose,kb:read"
    assert seen_headers["x-request-id"] == "req_knowledge_123"
    assert seen_headers["x-trace-id"] == "run_knowledge_456"
    assert seen_headers["x-parent-trace-id"] == "gateway_trace_789"
    assert "traceparent" not in seen_headers


@pytest.mark.asyncio
async def test_http_knowledge_forwards_w3c_traceparent_when_parent_trace_is_standard():
    seen_headers = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"hits": []})

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        transport=httpx.MockTransport(handler),
    )
    context = RetrievalContext(
        tenant_id="tenant_live",
        actor_user_id="user_prod",
        actor_roles=["admin", "user"],
        actor_scopes=["knowledge:diagnose", "kb:read"],
        request_id="req_knowledge_123",
        trace_id="run_knowledge_456",
        parent_trace_id=W3C_TRACE_ID,
    )

    await index.search("invoice", limit=1, context=context)

    assert seen_headers["x-parent-trace-id"] == W3C_TRACE_ID
    assert seen_headers["traceparent"].startswith(f"00-{W3C_TRACE_ID}-")
    assert seen_headers["traceparent"].endswith("-01")


@pytest.mark.asyncio
async def test_http_knowledge_parses_optional_upstream_trace_fields():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "document_id": "return_policy_v2",
                        "chunk_id": "return_policy_v2:4",
                        "title": "Return policy",
                        "content": "Damaged goods can be returned within 30 days.",
                        "score": 0.87,
                        "source_uri": "kb://return_policy_v2",
                    }
                ],
                "rewritten_queries": ["damaged order return", "broken item refund"],
                "candidates_by_stage": {"bm25": 15, "vector": 9, "reranked": 3, "selected": 1},
                "dropped_candidates": ["return_policy_v1:0", "shipping_policy_v3:2"],
            },
        )

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        transport=httpx.MockTransport(handler),
    )

    trace = await index.search("headphones broken", limit=1)

    assert trace.rewritten_queries == ["damaged order return", "broken item refund"]
    assert trace.candidates_by_stage == {"bm25": 15, "vector": 9, "reranked": 3, "selected": 1}
    assert trace.dropped_candidates == ["return_policy_v1:0", "shipping_policy_v3:2"]


@pytest.mark.asyncio
async def test_http_knowledge_ignores_unsafe_trace_payload():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "document_id": "invoice_policy_v1",
                        "title": "Invoice policy",
                        "content": "Invoices are issued within 24 hours.",
                        "source_uri": "kb://invoice_policy_v1",
                    }
                ],
                "rewritten_queries": {"unexpected": "shape"},
                "candidates_by_stage": {"vector": -1, "selected": True, "reranked": 1.5},
                "dropped_candidates": [None, {"id": "unsafe"}],
            },
        )

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        transport=httpx.MockTransport(handler),
    )

    trace = await index.search("invoice", limit=1)

    assert trace.rewritten_queries == ["invoice"]
    assert trace.candidates_by_stage == {"http": 1, "selected": 1}
    assert trace.dropped_candidates == []


@pytest.mark.asyncio
async def test_http_knowledge_returns_observable_trace_on_upstream_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        transport=httpx.MockTransport(handler),
    )

    trace = await index.search("invoice")

    assert trace.selected_context == []
    assert trace.selected_sources == []
    assert trace.candidates_by_stage["knowledge_http_503"] == 1
    assert trace.dropped_candidates == ["knowledge_http_503"]


@pytest.mark.asyncio
async def test_http_knowledge_retries_transient_error_before_returning_hits():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "document_id": "invoice_policy_v1",
                        "title": "Invoice policy",
                        "content": "Invoices are issued within 24 hours.",
                        "source_uri": "kb://invoice_policy_v1",
                    }
                ]
            },
        )

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        retry_attempts=2,
        retry_backoff_ms=0,
        transport=httpx.MockTransport(handler),
    )

    trace = await index.search("invoice", limit=1)

    assert calls == ["/knowledge/search", "/knowledge/search"]
    assert trace.selected_sources == ["kb://invoice_policy_v1"]
    assert index.circuit_status()["state"] == "closed"


@pytest.mark.asyncio
async def test_http_knowledge_opens_circuit_after_retryable_failures():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(503, json={"error": "temporary"})

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        retry_attempts=1,
        circuit_failure_threshold=1,
        circuit_reset_seconds=60,
        transport=httpx.MockTransport(handler),
    )

    first = await index.search("invoice")
    second = await index.search("invoice")

    assert first.dropped_candidates == ["knowledge_http_503"]
    assert second.dropped_candidates == ["knowledge_circuit_open"]
    assert calls == ["/knowledge/search"]
    assert index.circuit_status()["state"] == "open"


@pytest.mark.asyncio
async def test_http_knowledge_half_open_success_closes_circuit():
    now = 0.0
    calls = []

    def clock() -> float:
        return now

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json={"hits": []})

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        retry_attempts=1,
        circuit_failure_threshold=1,
        circuit_reset_seconds=10,
        transport=httpx.MockTransport(handler),
        clock=clock,
    )

    failed = await index.search("invoice")
    assert failed.dropped_candidates == ["knowledge_http_503"]
    assert index.circuit_status()["state"] == "open"

    now = 11.0
    recovered = await index.search("invoice")

    assert recovered.selected_context == []
    assert recovered.candidates_by_stage == {"http": 0, "selected": 0}
    assert calls == ["/knowledge/search", "/knowledge/search"]
    assert index.circuit_status()["state"] == "closed"
    assert index.circuit_status()["failure_count"] == 0


@pytest.mark.asyncio
async def test_http_knowledge_returns_observable_trace_on_bad_payload():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    index = HTTPKnowledgeIndex(
        base_url="https://knowledge.internal.test",
        transport=httpx.MockTransport(handler),
    )

    trace = await index.search("invoice")

    assert trace.selected_context == []
    assert trace.candidates_by_stage["knowledge_bad_payload"] == 1
