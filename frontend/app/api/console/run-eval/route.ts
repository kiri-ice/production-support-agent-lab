import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { EvalReport, JsonRecord } from "@/src/shared/types";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const parsed = await request.json().catch(() => ({}));
    const body: JsonRecord =
      typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
        ? (parsed as JsonRecord)
        : {};
    const report = await agentFetch<EvalReport>("/api/v1/admin/evals/golden", {
      method: "POST",
      body
    });
    return NextResponse.json(report);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}
