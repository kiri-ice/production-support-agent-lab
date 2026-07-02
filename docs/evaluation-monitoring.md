# 评测与在线监控

Agent 不能只靠“看起来回答不错”上线。这个项目使用离线 eval + 在线 monitor agent 双层保障。

## 失败时怎么定位

先看 eval 输出里的四个字段：

```json
{
  "case_id": "technical_audio_001",
  "failures": ["missing citation doc: troubleshooting_audio_v1"],
  "observed_intent": "technical_issue",
  "observed_tools": ["crm.get_customer"]
}
```

这个例子说明：意图和工具都对，但检索没有带出正确 citation。下一步应该看 `trace.retrieval`，而不是先改 prompt。

另一个例子：

```json
{
  "case_id": "guest_forbidden_001",
  "failures": ["forbidden order data leaked"],
  "observed_tools": ["order.get"]
}
```

这类失败要先查 ToolBroker 和资源归属校验，而不是让模型“注意隐私”。

## 离线 eval

测试集在 `examples/evals/golden_core.json`。

一个 case 包含：

```json
{
  "case_id": "refund_quality_001",
  "scenario": "质量问题退货咨询",
  "turns": [
    {"role": "user", "content": "我订单 A1001 的耳机坏了，能退吗？"}
  ],
  "expected": {
    "intent": "refund_or_return",
    "route_target": "order_agent",
    "route_needs_human": false,
    "required_entities": {"order_id": "A1001"},
    "required_allowed_tools": ["crm.get_customer", "order.get", "ticket.create"],
    "required_tools": ["crm.get_customer", "order.get", "ticket.create"],
    "required_tool_outputs": [
      {"tool_name": "order.get", "path": "order_id", "equals": "A1001"}
    ],
    "must_include": ["质量问题", "30 天", "售后工单"],
    "must_not_include": ["无条件退款"],
    "escalation": false,
    "policy_refs": ["return_policy_v3"]
  }
}
```

这样评测的是端到端行为：

- 分类是否正确。
- 置信度、实体、缺失槽位是否符合预期。
- 路由目标、`needs_human` 和工具白名单是否正确。
- 工具是否调对。
- 多轮 memory facts 和关键工具输出是否符合预期。
- policy finding 是否按预期出现，或没有被误判出来。
- 是否有必须信息。
- 是否避免违规承诺。
- 是否正确人工升级。
- citation 是否来自正确政策。

运行：

```bash
python scripts/run_eval.py
```

## EvalExpectation 字段速查

| 字段 | 断言什么 | 何时使用 | 示例 |
| --- | --- | --- | --- |
| `intent` | 最后一轮主意图 | 判断分类是否正确 | `golden_core.json` |
| `min_confidence` | 最低置信度 | 防止 hard case 低置信度误过 | `memory_multiturn_regression.json` |
| `route_target` | 最后一轮 route | 验证多 agent routing | `routing_regression.json` |
| `route_needs_human` | 是否需要人工 | 投诉、安全、失败降级 | `routing_regression.json` |
| `required_entities` | 实体抽取结果 | 订单号、上一单、发票主题 | `memory_multiturn_regression.json` |
| `required_missing_slots` | 必须缺失的槽位 | 需要追问的流程 | `routing_regression.json` |
| `forbidden_missing_slots` | 不应该缺失的槽位 | memory 应该补齐时 | `memory_multiturn_regression.json` |
| `required_memory_facts` | 会话 memory 最终状态 | 多轮对话回归 | `memory_multiturn_regression.json` |
| `expected_turns` | 每一轮 intent、route、tool、error | 多轮链路逐轮校验 | `memory_multiturn_regression.json` |
| `required_allowed_tools` | route 白名单 | 防止越权工具进入 route | `routing_regression.json` |
| `forbidden_allowed_tools` | 禁止出现的工具白名单 | 安全/账号类问题 | `routing_regression.json` |
| `required_tools` | 成功调用过的工具 | 端到端工具链路 | `golden_core.json` |
| `required_tool_outputs` | 工具输出里的关键字段 | 证明 memory 真的进了工具参数 | `memory_multiturn_regression.json` |
| `required_error_codes` | trace 中的工具错误码 | 上游失败、越权、超时 | `tool_failure_regression.json` |
| `required_policy_codes` | policy finding | prompt injection、PII 等 | `security_regression.json` |
| `forbidden_policy_codes` | 不应出现的 policy finding | 防止误杀正常请求 | `routing_regression.json` |
| `must_include` | 最终回答必须包含 | 用户可见承诺和解释 | `golden_core.json` |
| `must_not_include` | 最终回答不得包含 | 禁止编造、禁止违规承诺 | `tool_failure_regression.json` |
| `escalation` | 是否人工升级 | 投诉、安全、不可恢复失败 | `golden_core.json` |
| `policy_refs` | citation 文档 id | RAG grounding | `retrieval_challenge.json` |

经验法则：修 intent 时断言 `intent/entities/missing_slots`；修 routing 时断言 `route_target/allowed_tools`；修工具失败时断言 `required_error_codes/must_not_include`；修多轮记忆时断言 `expected_turns/required_memory_facts/required_tool_outputs`。

## 离线 monitor regression

回答 eval 只能证明单条 case 的行为正确。Monitor regression 验证的是“线上质量信号是否会被聚合出来”。

运行：

```bash
python scripts/run_monitor_eval.py
```

`examples/evals/monitor_regression.json` 会重放一组生产味更重的流量：

- 正常物流查询。
- prompt injection。
- 跨用户订单访问。
- 物流供应商超时。
- 投诉人工接管。

它不检查最终回答文本，而是检查 `MonitorSummary`：

- `by_risk_level`：风险分布是否符合预期。
- `by_failure_type`：`PROMPT_INJECTION_ATTEMPT`、`FORBIDDEN`、`TIMEOUT` 是否被捕获。
- `policy_compliance_rate`：policy 风险是否拉低合规率。
- `human_review_rate`：人工接管压力是否可见。
- `required_alerts`：P1/P2 alert 是否按 failure type 或 `QUALITY_REVIEW` 聚合。

这类 eval 很适合放在发布前 staging replay：模型、prompt、工具、路由可以变，但线上 monitor 的告警契约不能悄悄失效。

## 在线 monitor agent

`OnlineMonitorAgent` 在本地 lab 中同进程消费 `AgentResponse`，生成 `MonitorEvent`。生产环境应改成异步队列消费者。

它检查：

- 是否有高风险 policy finding。
- 工具是否失败。
- 是否需要人工复核。
- 是否有 grounding/citation。
- 失败类型如何聚合。

生产中可以把 monitor 改成队列消费者：

```text
agent.run.completed -> Kafka/SQS/Redis Stream -> monitor worker -> alert/dashboard
```

本地 demo 里还提供了一个同步汇总入口：

```bash
curl http://127.0.0.1:8000/api/v1/admin/monitor/summary \
  -H "X-Demo-Role: admin"
```

它会输出：

- `by_risk_level`：风险等级分布。
- `by_intent`：每类业务意图的线上量级。
- `by_failure_type`：工具错误、越权、prompt injection、grounding 不足等失败类型。
- `grounded_rate`、`policy_compliance_rate`、`human_review_rate`：可以直接放进 dashboard 的基础质量指标。
- `alerts`：按 `agent_version + intent + failure_type` 聚合后的 P0-P3 告警。

当前优先级规则很朴素，但适合学习生产思路：

- `P0`：输出 PII 泄露或 critical 风险。`PolicyEngine.check_output` 会把手机号/邮箱输出标记为 `PII_IN_OUTPUT`，`OnlineMonitorAgent` 会聚合成 P0。
- `P1`：高风险 policy finding，或输出不满足 policy。
- `P2`：工具失败、需要人工复核、citation/grounding 不足。
- `P3`：其他需要观察的质量问题。

## 不要过度依赖 LLM-as-judge

LLM judge 适合评估表达质量、同理心、覆盖度。关键事实不要只交给 judge：

- 退款资格。
- 金额计算。
- PII 泄露。
- 工具参数。
- 是否越权。

这些应该用规则、gold label、工具 fixture 和引用校验。
