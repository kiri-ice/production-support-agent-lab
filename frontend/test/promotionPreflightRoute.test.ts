import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "../app/api/console/promotion/preflights/route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  vi.restoreAllMocks();
  process.env = { ...ORIGINAL_ENV };
});

describe("promotion preflight BFF route", () => {
  it("creates a sanitized deep ops preflight record", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        id: "preflight_123",
        tenant_id: "demo_tenant",
        environment: "staging",
        target_version: "agent-next",
        gate_status: "passed",
        gate_fingerprint: "gate_fp_preflight",
        gate: {
          status: "passed",
          generated_at: "2026-07-05T00:00:00Z",
          environment: "staging",
          source: "event_store",
          window_hours: 24,
          thresholds: {
            max_active_p0p1_alerts: 0,
            max_active_alerts: 10,
            max_tool_failure_rate: 0.05,
            max_feedback_negative_rate: 0.4,
            max_eval_age_hours: 24,
            min_tool_calls: 1,
            min_feedback_count: 5
          },
          checks: [],
          readiness: { status: "ok", environment: "staging", deep: true, ops: true, checks: [] },
          monitor: {},
          tool_audit: {},
          feedback: {},
          latest_eval_gate: null
        },
        actor_user_id: "user_demo",
        created_at: "2026-07-05T00:00:00Z",
        expires_at: "2026-07-05T00:30:00Z"
      })
    );

    const response = await POST(
      jsonRequest("/api/console/promotion/preflights", {
        target_version: "agent-next",
        source: "file",
        deep: false,
        ops: false,
        window_hours: 999,
        max_tool_failure_rate: -1,
        min_feedback_count: -5,
        expires_in_minutes: 999
      })
    );

    expect(response.status).toBe(200);
    const [target, init] = fetchMock.mock.calls[0];
    expect(String(target)).toBe("http://agent.internal/api/v1/admin/promotion/preflights");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      target_version: "agent-next",
      source: "event_store",
      deep: true,
      ops: true,
      window_hours: 168,
      max_tool_failure_rate: 0,
      min_feedback_count: 0,
      expires_in_minutes: 240
    });
  });

  it("lists recent preflight records with bounded query parameters", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));

    const response = await GET(getRequest("/api/console/promotion/preflights?limit=999&order=old"));

    expect(response.status).toBe(200);
    const [target] = fetchMock.mock.calls[0];
    const url = new URL(String(target));
    expect(url.pathname).toBe("/api/v1/admin/promotion/preflights");
    expect(url.searchParams.get("limit")).toBe("100");
    expect(url.searchParams.get("order")).toBe("desc");
  });
});

function getRequest(path: string) {
  return { nextUrl: new URL(`http://console.local${path}`) } as unknown as NextRequest;
}

function jsonRequest(path: string, body: unknown) {
  return new Request(`http://console.local${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }) as unknown as NextRequest;
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}
