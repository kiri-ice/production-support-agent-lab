# Product Design brief gate

The repository currently ships a backend service, API docs, evals, runbooks, and production checks. It does not yet include a frontend, screenshots, Figma source, brand system, or visual reference. Product Design work should therefore start with a brief confirmation and visual exploration before any UI is built.

## Candidate product surface

The most useful first UI is an operator console for production support-agent operations. It should help an on-call operator or Agent beginner answer:

- What happened in a specific conversation or run?
- Which intent, route, tools, retrieval hits, policy findings, and monitor event caused an alert?
- Did a tool fail because of auth, schema, timeout, upstream 5xx, replay, or missing retrieval?
- Which regression file should receive the real failure sample?
- Has someone acknowledged, investigated, or resolved a monitor alert?

## Backend API map

| Console area | Backend endpoint | Why it matters |
| --- | --- | --- |
| Run trace | `GET /api/v1/agent/runs/{run_id}` | Shows intent, route, retrieval, tools, spans, and LLM fallback status. |
| Incident bundle | `GET /api/v1/admin/incidents/runs/{run_id}?include_memory=true` | One response with run, monitor events, tool audit, and optional memory replay. |
| Tool audit | `GET /api/v1/admin/tools/audit?trace_id=...` | Durable tool facts without raw arguments or PII. |
| Monitor summary | `GET /api/v1/admin/monitor/summary?source=event_store` | Aggregates live quality by risk, intent, failure type, grounded rate, and alerts. |
| Monitor events | `GET /api/v1/admin/monitor/events?source=event_store` | Raw structured monitor events for sampling and replay. |
| Alert triage | `GET/POST /api/v1/admin/monitor/alerts/{alert_key}/triage` | Append-only ack/investigate/resolve workflow. |
| Event log | `GET /api/v1/admin/events?conversation_id=...` | Auditable event stream for messages, runs, monitor, and triage. |
| Memory replay | `GET /api/v1/admin/conversations/{conversation_id}/memory/replay` | Rebuilds conversation facts after restart. |

## Product Design questions to confirm

Before ideation or implementation, confirm:

1. Which screen comes first: operations overview, incident/run detail, monitor alerts, eval report, or tool audit?
2. What visual source should it match: an existing admin console, Figma file, screenshot, design system, or a new restrained operations-tool style?
3. Interactivity level: full working console wired to local API, or a faster static prototype?

## Suggested first brief

Build a production operations console for this support-agent backend. Start with an incident/run detail view: left rail of monitor alerts, main trace timeline, right side panels for citations, tool audit, memory replay, and triage history. Use a restrained Agent-operations style, dense but readable, with full interactivity against local API endpoints.

This is only a proposed brief. Product Design implementation should not start until the user confirms the brief and chooses a visual direction.
