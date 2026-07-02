from __future__ import annotations

import hashlib
import json
from typing import Any

from support_agent_lab.tools.registry import Actor, ToolBroker, ToolContext
from support_agent_lab.models import new_id


class MCPToolAdapter:
    """A small MCP-shaped adapter over the ToolBroker.

    The project keeps this adapter dependency-light so the core lab runs without
    an MCP runtime. Install the optional `mcp` extra to expose the same registry
    through a real MCP server.
    """

    def __init__(self, broker: ToolBroker, tenant_id: str, allow_default_actor: bool = True) -> None:
        self.broker = broker
        self.tenant_id = tenant_id
        self.allow_default_actor = allow_default_actor

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item["name"],
                "description": item["description"],
                "inputSchema": item["input_schema"],
            }
            for item in self.broker.registry.list_tools()
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        user_id: str | None = None,
        scopes: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not user_id:
            if not self.allow_default_actor:
                raise RuntimeError("MCP production calls must include an authenticated user_id")
            user_id = "user_demo"
        if scopes is None and not self.allow_default_actor:
            raise RuntimeError("MCP production calls must include authenticated scopes")
        resolved_scopes = scopes or ["crm:read", "order:read", "shipping:read", "ticket:write", "kb:read"]
        ctx = ToolContext(
            actor=Actor(
                user_id=user_id,
                tenant_id=self.tenant_id,
                scopes=resolved_scopes,
            ),
            request_id=new_id("mcp_req"),
            trace_id=new_id("mcp_trace"),
            tenant_id=self.tenant_id,
            idempotency_key=idempotency_key or self._stable_idempotency_key(name, arguments, user_id),
        )
        result = await self.broker.call(name, arguments, ctx)
        return {
            "content": [{"type": "json", "json": result.model_dump(mode="json")}],
            "isError": result.status.value != "success",
        }

    def _stable_idempotency_key(self, name: str, arguments: dict[str, Any], user_id: str) -> str | None:
        if not any(part in name for part in ["create", "cancel", "update", "add", "upsert"]):
            return None
        payload = json.dumps(
            {
                "tenant_id": self.tenant_id,
                "user_id": user_id,
                "name": name,
                "arguments": arguments,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
