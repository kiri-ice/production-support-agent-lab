import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "../app/api/console/feedback/reviews/route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  vi.restoreAllMocks();
  process.env = { ...ORIGINAL_ENV };
});

describe("feedback review BFF route", () => {
  it("proxies bounded review trail requests", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([
        {
          id: "fdbrv_1",
          tenant_id: "demo_tenant",
          feedback_id: "fdbk_1",
          conversation_id: "conv_1",
          run_id: "run_1",
          status: "acknowledged",
          assignee_user_id: null,
          actor_user_id: "operator",
          note: "reviewing",
          created_at: "2026-07-06T00:00:00Z"
        }
      ])
    );

    const response = await GET(
      getRequest("/api/console/feedback/reviews?feedbackId=fdbk_1&limit=999&order=desc")
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toHaveLength(1);
    const [target] = fetchMock.mock.calls[0];
    const url = new URL(String(target));
    expect(url.pathname).toBe("/api/v1/admin/feedback/fdbk_1/reviews");
    expect(url.searchParams.get("limit")).toBe("200");
    expect(url.searchParams.get("order")).toBe("desc");
  });

  it("forwards sanitized review actions", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        id: "fdbrv_2",
        tenant_id: "demo_tenant",
        feedback_id: "fdbk_1",
        conversation_id: "conv_1",
        run_id: "run_1",
        status: "resolved",
        assignee_user_id: "ops",
        actor_user_id: "operator",
        note: "done",
        created_at: "2026-07-06T00:00:00Z"
      })
    );

    const response = await POST(
      jsonRequest("/api/console/feedback/reviews", {
        feedbackId: " fdbk_1 ",
        status: "resolved",
        assigneeUserId: " ops ",
        note: " done "
      })
    );

    expect(response.status).toBe(200);
    const [target, init] = fetchMock.mock.calls[0];
    expect(String(target)).toBe("http://agent.internal/api/v1/admin/feedback/fdbk_1/reviews");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      status: "resolved",
      assignee_user_id: "ops",
      note: "done"
    });
  });

  it("rejects missing feedback id and invalid status before proxying", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    const missing = await GET(getRequest("/api/console/feedback/reviews"));
    const invalid = await POST(
      jsonRequest("/api/console/feedback/reviews", {
        feedbackId: "fdbk_1",
        status: "closed"
      })
    );

    expect(missing.status).toBe(400);
    expect(await missing.json()).toEqual({ detail: "feedbackId is required" });
    expect(invalid.status).toBe(400);
    expect(await invalid.json()).toEqual({ detail: "Invalid feedback review status" });
    expect(fetchMock).not.toHaveBeenCalled();
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
