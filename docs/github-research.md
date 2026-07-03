# GitHub research notes

This project is not trying to clone a benchmark or become a full platform. The research below is used as design pressure: what production agent systems tend to need, and which pieces this lab should teach explicitly.

## References reviewed

| Reference | What it is useful for | What this project adopts | What remains outside this lab |
| --- | --- | --- | --- |
| [openai/openai-cs-agents-demo](https://github.com/openai/openai-cs-agents-demo) | Customer-service agent demo with a Python orchestration backend and a frontend. | The domain is close, but this lab emphasizes backend readability, evals, event logs, auth, tool governance, and production runbooks. | A polished customer-service UI waits for Product Design brief confirmation. |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | General multi-agent SDK, Responses API integration, handoffs, guardrails, and tracing ideas. | This lab keeps the orchestration explicit in ordinary Python so backend engineers can inspect every state transition. | Full SDK feature parity, hosted tracing UI, and broad model/provider routing. |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | Reference MCP servers and examples of standardizing tool boundaries. | This lab implements an MCP-shaped adapter and scope/idempotency semantics around `ToolBroker`. | A hardened production MCP gateway with session auth, transport-level controls, and enterprise permission manifests. |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Stateful, long-running graph orchestration and multi-agent coordination. | This lab models routing, trace spans, memory replay, and handoff decisions in a modular monolith. | Graph runtime, distributed checkpointing, and dynamic agent graphs. |
| [langfuse/langfuse](https://github.com/langfuse/langfuse) | LLM observability, evals, prompt management, and debugging workflows. | This lab includes structured traces, monitor events, alert triage, and offline evals as backend primitives. | Full dashboard, prompt registry, ClickHouse/warehouse storage, and hosted observability UX. |
| [Arize Phoenix](https://github.com/arize-ai/phoenix) | Open-source AI observability and evaluation, with tracing and troubleshooting focus. | This lab mirrors the core idea that traces and evals are first-class production artifacts. | OpenTelemetry/OpenInference exporters and a notebook/dashboard-first observability platform. |
| [infiniflow/ragflow](https://github.com/infiniflow/ragflow) | Production-scale RAG workflow and retrieval product surface. | This lab teaches retrieval trace, query rewrite, CJK tokenization, citations, and retrieval challenge evals. | Full document ingestion, vector/BM25 infra, reranker services, tenant-scale RAG UI. |
| [Ragas](https://docs.ragas.io/en/stable/) | Systematic RAG evaluation loops and component-level metrics. | This lab uses deterministic retrieval challenge evals and citation assertions before introducing judge-based scoring. | Reference-free LLM-as-judge metrics and synthetic test generation are future extensions. |

## Design decisions this reinforces

- Keep the first implementation small enough to read end to end, but do not hide production concerns behind a single prompt.
- Make every tool call typed, scoped, timeout-bounded, idempotent where needed, and audited.
- Treat retrieval as a debuggable subsystem: query rewrite, candidate counts, selected context, citations, and regression cases are all visible.
- Treat memory as both working state and event-sourced replay, because production incidents often happen after process restarts.
- Keep monitor signals structured enough to aggregate by agent version, intent, failure type, and sample run ids.
- Teach production migration honestly: SQLite and in-process monitor are a single-instance baseline; Redis/Postgres/Kafka/warehouse/exporters are the scale-up path.

## Gaps intentionally left explicit

- Production MCP gateway hardening is documented, not bundled.
- Full observability dashboards are documented through APIs and future Product Design work, not shipped as an invented UI.
- RAG answerability and unsupported-claim detection are roadmap items after deterministic retrieval/citation gates.
- True multi-instance deployment needs Postgres/Redis/Kafka replacements for SQLite event, nonce, idempotency, and monitor storage.
