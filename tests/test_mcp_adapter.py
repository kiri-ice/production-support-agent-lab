import pytest

from support_agent_lab.bootstrap import create_container
from support_agent_lab.mcp.adapter import MCPToolAdapter


@pytest.mark.asyncio
async def test_mcp_adapter_applies_stable_idempotency_for_write_tools():
    container = create_container()
    adapter = MCPToolAdapter(container.tools, tenant_id="demo_tenant")
    payload = {
        "customer_id": "SELF",
        "title": "MCP ticket",
        "description": "Created through MCP adapter",
    }

    first = await adapter.call_tool("ticket.create", payload, user_id="user_demo", scopes=["ticket:write"])
    second = await adapter.call_tool("ticket.create", payload, user_id="user_demo", scopes=["ticket:write"])

    first_result = first["content"][0]["json"]
    second_result = second["content"][0]["json"]
    assert first["isError"] is False
    assert first_result["data"]["ticket_id"] == second_result["data"]["ticket_id"]


@pytest.mark.asyncio
async def test_mcp_adapter_respects_resource_ownership():
    container = create_container()
    adapter = MCPToolAdapter(container.tools, tenant_id="demo_tenant")

    result = await adapter.call_tool(
        "order.get",
        {"order_id": "A1001"},
        user_id="user_guest",
        scopes=["order:read"],
    )

    payload = result["content"][0]["json"]
    assert result["isError"] is True
    assert payload["error_code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_mcp_adapter_requires_explicit_actor_when_default_actor_disabled():
    container = create_container()
    adapter = MCPToolAdapter(container.tools, tenant_id="demo_tenant", allow_default_actor=False)

    with pytest.raises(RuntimeError, match="authenticated user_id"):
        await adapter.call_tool("crm.get_customer", {"user_id": "user_demo"})
