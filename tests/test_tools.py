import pytest

from support_agent_lab.bootstrap import create_container
from support_agent_lab.models import ToolStatus
from support_agent_lab.tools.registry import Actor, ToolContext


@pytest.mark.asyncio
async def test_write_tool_requires_idempotency_key():
    container = create_container()
    ctx = ToolContext(
        actor=Actor(
            user_id="user_demo",
            tenant_id="demo_tenant",
            scopes=["ticket:write"],
        ),
        request_id="req_1",
        trace_id="trace_1",
        tenant_id="demo_tenant",
    )

    result = await container.tools.call(
        "ticket.create",
        {
            "customer_id": "cust_1001",
            "title": "Need help",
            "description": "A write without idempotency should fail.",
        },
        ctx,
    )

    assert result.status == ToolStatus.failed
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_idempotent_replay_returns_first_write_result():
    container = create_container()
    ctx = ToolContext(
        actor=Actor(
            user_id="user_demo",
            tenant_id="demo_tenant",
            scopes=["ticket:write"],
        ),
        request_id="req_1",
        trace_id="trace_1",
        tenant_id="demo_tenant",
        idempotency_key="same-ticket",
    )
    payload = {
        "customer_id": "cust_1001",
        "title": "Need help",
        "description": "The same request may be replayed safely.",
    }

    first = await container.tools.call("ticket.create", payload, ctx)
    second = await container.tools.call("ticket.create", payload, ctx)

    assert first.status == ToolStatus.success
    assert second.status == ToolStatus.success
    assert first.data["ticket_id"] == second.data["ticket_id"]


@pytest.mark.asyncio
async def test_order_tool_enforces_customer_ownership():
    container = create_container()
    ctx = ToolContext(
        actor=Actor(
            user_id="user_guest",
            tenant_id="demo_tenant",
            scopes=["order:read"],
        ),
        request_id="req_1",
        trace_id="trace_1",
        tenant_id="demo_tenant",
    )

    result = await container.tools.call("order.get", {"order_id": "A1001"}, ctx)

    assert result.status == ToolStatus.failed
    assert result.error_code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_shipping_tool_enforces_customer_ownership():
    container = create_container()
    ctx = ToolContext(
        actor=Actor(
            user_id="user_guest",
            tenant_id="demo_tenant",
            scopes=["shipping:read"],
        ),
        request_id="req_1",
        trace_id="trace_1",
        tenant_id="demo_tenant",
    )

    result = await container.tools.call("shipping.track", {"logistics_id": "YT99887766CN"}, ctx)

    assert result.status == ToolStatus.failed
    assert result.error_code == "FORBIDDEN"
