# MCP 与工具治理

MCP 的价值不是“让模型能调函数”这么简单，而是把业务系统包装成安全、结构化、可审计的能力边界。

## 三个最小实验

成功创建工单：

```python
result = await broker.call("ticket.create", payload, ctx_with_ticket_write_scope_and_idempotency_key)
assert result.status == "success"
```

缺少权限：

```python
ctx.actor.scopes = []
result = await broker.call("ticket.create", payload, ctx)
assert result.error_code == "FORBIDDEN"
```

缺少幂等键：

```python
ctx.idempotency_key = None
result = await broker.call("ticket.create", payload, ctx)
assert result.error_code == "VALIDATION_ERROR"
```

跨用户资源访问：

```python
guest_ctx.actor.user_id = "user_guest"
result = await broker.call("order.get", {"order_id": "A1001"}, guest_ctx)
assert result.error_code == "FORBIDDEN"
```

对应测试见 `tests/test_tools.py` 和 `tests/test_mcp_adapter.py`。

## 工具契约

每个工具在 `ToolDefinition` 中声明：

```python
ToolDefinition(
    name="ticket.create",
    description="Create a support ticket for follow-up or human handoff.",
    input_model=CreateTicketInput,
    output_model=CreateTicketOutput,
    required_scopes=["ticket:write"],
    timeout_ms=2000,
    idempotent=False,
    handler=...
)
```

工具调用统一进入 `ToolBroker.call`：

```text
lookup tool
  -> authorize scopes and tenant
  -> validate input schema
  -> require idempotency key for write tools
  -> apply timeout
  -> validate output schema
  -> store idempotent result
  -> append audit record
```

## 为什么写操作必须幂等

客服 Agent 很容易遇到这些情况：

- 网络超时，但上游已经创建了工单。
- 用户重复点击。
- Agent retry。
- 线上回放或灾难恢复。

如果 `ticket.create`、`refund.create`、`order.cancel` 没有幂等键，重试可能造成重复建单、重复退款或重复取消。

本项目规则：

- 只读工具默认 idempotent。
- 写工具必须带 `idempotency_key`。
- 相同 key + 相同 payload 返回第一次结果。
- 相同 key + 不同 payload 返回 `IDEMPOTENCY_CONFLICT`。

## MCP adapter

`src/support_agent_lab/mcp/adapter.py` 提供 dependency-light 的 MCP-shaped adapter：

```python
adapter.list_tools()
await adapter.call_tool("order.get", {"order_id": "A1001"})
```

安装可选依赖后可启动 MCP server：

```bash
pip install -e ".[mcp]"
python -m support_agent_lab.mcp.server
```

生产中建议继续保留 `ToolBroker`，不要让 MCP server 绕过权限、审计和幂等。

## 常见工具设计错误

- 暴露 `execute_sql` 这种万能工具。
- 只校验输入，不校验输出。
- 工具返回大段自然语言，而不是结构化数据。
- 写工具没有幂等键。
- 权限只看角色，不校验 tenant 或 resource。
- 审计日志记录完整 PII 或 token。
- timeout 后没有取消上游请求。
