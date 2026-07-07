import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "../app/api/console/readiness/route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  vi.restoreAllMocks();
  process.env = { ...ORIGINAL_ENV };
});

describe("console readiness BFF route", () => {
  it("proxies deep ops readiness with bounded query parameters", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        status: "ok",
        environment: "production",
        deep: true,
        ops: true,
        checks: [
          { name: "config", status: "ok", detail: "settings validated" },
          { name: "alert_dispatcher_worker", status: "skipped", detail: "alert webhook disabled" },
          { name: "monitor_review_worker", status: "ok", detail: "status=active" },
          { name: "audit_export_batch", status: "ok", detail: "status=fresh" }
        ]
      })
    );

    const response = await GET(getRequest("/api/console/readiness?deep=true&ops=true&limit=999"));

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.ops).toBe(true);
    const [target] = fetchMock.mock.calls[0];
    const url = new URL(String(target));
    expect(url.pathname).toBe("/api/v1/ready");
    expect(url.searchParams.get("deep")).toBe("true");
    expect(url.searchParams.get("ops")).toBe("true");
    expect(url.searchParams.has("limit")).toBe(false);
  });

  it("returns backend readiness failure details without raw response passthrough", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        {
          detail: "ops readiness failed: worker missing",
          raw_payload: "PRIVATE_BACKEND_DEBUG"
        },
        503
      )
    );

    const response = await GET(getRequest("/api/console/readiness?deep=true&ops=true"));

    expect(response.status).toBe(503);
    const body = await response.json();
    expect(body).toEqual({ detail: "ops readiness failed: worker missing" });
    expect(JSON.stringify(body)).not.toContain("PRIVATE_BACKEND_DEBUG");
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
