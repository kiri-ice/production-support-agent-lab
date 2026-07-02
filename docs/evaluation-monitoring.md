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
    "required_tools": ["crm.get_customer", "order.get", "ticket.create"],
    "must_include": ["质量问题", "30 天", "售后工单"],
    "must_not_include": ["无条件退款"],
    "escalation": false,
    "policy_refs": ["return_policy_v3"]
  }
}
```

这样评测的是端到端行为：

- 分类是否正确。
- 工具是否调对。
- 是否有必须信息。
- 是否避免违规承诺。
- 是否正确人工升级。
- citation 是否来自正确政策。

运行：

```bash
python scripts/run_eval.py
```

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

## 不要过度依赖 LLM-as-judge

LLM judge 适合评估表达质量、同理心、覆盖度。关键事实不要只交给 judge：

- 退款资格。
- 金额计算。
- PII 泄露。
- 工具参数。
- 是否越权。

这些应该用规则、gold label、工具 fixture 和引用校验。
