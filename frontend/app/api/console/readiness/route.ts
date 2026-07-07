import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { ReadinessResponse } from "@/src/shared/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const deep = request.nextUrl.searchParams.get("deep") === "true";
  const ops = request.nextUrl.searchParams.get("ops") === "true";

  try {
    const report = await agentFetch<ReadinessResponse>("/api/v1/ready", {
      query: { deep, ops }
    });
    return NextResponse.json(report);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}
