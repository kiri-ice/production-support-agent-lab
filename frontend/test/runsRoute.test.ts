import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET as runsGet } from "../app/api/console/runs/route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  vi.restoreAllMocks();
  process.env = { ...ORIGINAL_ENV };
});

describe("runs BFF route", () => {
  it("forwards request and parent trace filters to the backend", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: "run_1",
            conversation_id: "conv_1",
            user_id: "user_demo",
            request_id: "gateway_req_123",
            parent_trace_id: "gateway_trace_456",
            agent_version: "agent_2026_07_lab",
            intent: "order_status",
            route: "order_agent",
            status: "completed",
            created_at: "2026-07-06T00:00:00Z",
            completed_at: "2026-07-06T00:00:01Z",
            duration_ms: 1000,
            tool_count: 2,
            failed_tool_count: 0,
            tool_error_codes: [],
            policy_codes: [],
            citation_count: 1,
            llm_call_count: 1,
            needs_human: false
          }
        ],
        total: 1,
        limit: 25,
        offset: 0,
        has_more: false
      })
    );

    const response = await runsGet(
      getRequest("/api/console/runs?requestId=gateway_req_123&parentTraceId=gateway_trace_456&q=gateway_req")
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ total: 1 });
    const [target] = fetchMock.mock.calls[0];
    const url = new URL(String(target));
    expect(url.pathname).toBe("/api/v1/admin/runs");
    expect(url.searchParams.get("request_id")).toBe("gateway_req_123");
    expect(url.searchParams.get("parent_trace_id")).toBe("gateway_trace_456");
    expect(url.searchParams.get("q")).toBe("gateway_req");
  });
});

function getRequest(path: string) {
  return { nextUrl: new URL(`http://console.local${path}`) } as unknown as NextRequest;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}
