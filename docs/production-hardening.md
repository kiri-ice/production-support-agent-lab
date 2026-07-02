# 生产化加固路线

本项目能本地跑，但它刻意保留了生产化接口。下面是上线前需要补齐的能力。

## 当前 mock 到生产实现的替换表

| 当前模块 | 当前实现 | 生产实现 |
| --- | --- | --- |
| ConversationMemory | Python dict | PostgreSQL + Redis |
| DemoStore | 本地订单/客户 fixture | CRM、OMS、Ticketing API |
| KnowledgeIndex | 简单 tokenizer + scorer | pgvector + BM25 + reranker |
| OnlineMonitorAgent | 同进程 list | Queue worker + OLAP/dashboard |
| LLMGateway | Mock provider | Real provider routing + fallback + budget |
| SQLiteEventStore | local SQLite events | Postgres append-only events + Kafka stream |
| Tool audit | 内存 audit_log | append-only audit table |
| PolicyEngine | regex + rule | PII detector + RBAC + compliance engine |
| API auth | demo header actor + admin role | JWT/session/API key + tenant isolation |
| Trace | Pydantic object | OpenTelemetry spans |

## 数据层

把内存 store 换成数据库：

- `tenants`
- `users`
- `conversations`
- `messages`
- `agent_runs`
- `tool_calls`
- `knowledge_documents`
- `knowledge_chunks`
- `tickets`
- `audit_logs`
- `monitor_events`

所有表都带 `tenant_id`。

## 安全

- API 鉴权：JWT、session 或 API key。
- 管理后台 RBAC。
- 工具 scope 和资源级权限。
- PII 加密或哈希。
- 日志默认脱敏。
- Webhook 验签。
- Secret 走 Secret Manager。
- 高风险工具二次确认。

## 可观测性

一次 agent run 应拆成 trace span：

```text
chat.receive
conversation.load
intent.detect
policy.input_check
route.decide
knowledge.retrieve
tool.invoke
policy.output_check
message.persist
monitor.review
```

指标：

- p50/p95 latency
- token cost
- tool success rate
- retrieval empty rate
- handoff rate
- policy violation rate
- CSAT
- repeated contact rate

## 发布策略

- PR 跑 unit tests 和 golden eval。
- merge 前跑 regression、tool failure、retrieval challenge。
- 发布前 staging replay。
- canary 1% 流量。
- P0/P1 自动告警和回滚。

## 阶段拆分

1. 模块化单体。
2. API/worker 分离。
3. Tool Service 独立。
4. Knowledge Service 独立。
5. LLM Gateway 独立。
6. 多租户成本中心、审计中心、灰度平台。
