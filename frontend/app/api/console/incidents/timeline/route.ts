import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { IncidentTimelineResponse } from "@/src/shared/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const runId = searchParams.get("runId")?.trim();
  if (!runId) {
    return NextResponse.json({ detail: "runId is required" }, { status: 400 });
  }
  const includeConversationContext = searchParams.get("include_conversation_context") !== "false";
  const limit = clampNumber(searchParams.get("limit"), 1, 1000, 500);

  try {
    const response = await agentFetch<IncidentTimelineResponse>(
      `/api/v1/admin/incidents/runs/${encodeURIComponent(runId)}/timeline`,
      {
        query: {
          include_conversation_context: includeConversationContext,
          limit
        }
      }
    );
    return NextResponse.json(response);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}

function clampNumber(value: unknown, min: number, max: number, fallback: number) {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}
