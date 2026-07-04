import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { MonitorDrilldownResponse } from "@/src/shared/types";

export const dynamic = "force-dynamic";

const QUERY_KEYS = [
  "source",
  "alert_key",
  "intent",
  "risk_level",
  "failure_type",
  "created_after",
  "created_before",
  "needs_human_review",
  "grounded",
  "policy_compliant",
  "include_healthy",
  "limit",
  "order"
] as const;

export async function GET(request: NextRequest) {
  try {
    const query: Record<string, string> = {};
    for (const key of QUERY_KEYS) {
      const value = request.nextUrl.searchParams.get(key);
      if (value) {
        query[key] = value;
      }
    }
    const drilldown = await agentFetch<MonitorDrilldownResponse>("/api/v1/admin/monitor/drilldown", {
      query
    });
    return NextResponse.json(drilldown);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}
