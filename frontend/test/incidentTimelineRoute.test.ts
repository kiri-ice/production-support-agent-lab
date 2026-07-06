import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "../app/api/console/incidents/timeline/route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  vi.restoreAllMocks();
  process.env = { ...ORIGINAL_ENV };
});

describe("incident timeline BFF route", () => {
  it("proxies sanitized timeline requests with bounded query params", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.internal";
    process.env.FRONTEND_AUTH_MODE = "demo";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        schema_version: "incident_timeline.v1",
        generated_at: "2026-07-06T00:00:00.000Z",
        run_id: "run_1",
        conversation_id: "conv_1",
        run_source: "event_store",
        entry_count: 1,
        entries: [],
        redactions: ["message_content"]
      })
    );

    const response = await GET(
      getRequest("/api/console/incidents/timeline?runId=run_1&include_conversation_context=false&limit=999999")
    );

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.schema_version).toBe("incident_timeline.v1");
    const [target] = fetchMock.mock.calls[0];
    const url = new URL(String(target));
    expect(url.pathname).toBe("/api/v1/admin/incidents/runs/run_1/timeline");
    expect(url.searchParams.get("include_conversation_context")).toBe("false");
    expect(url.searchParams.get("limit")).toBe("1000");
  });

  it("requires a run id", async () => {
    const response = await GET(getRequest("/api/console/incidents/timeline"));

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ detail: "runId is required" });
  });
});

function getRequest(path: string) {
  return { nextUrl: new URL(`http://console.local${path}`) } as unknown as NextRequest;
}
