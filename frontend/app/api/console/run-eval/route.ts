import { NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { EvalReport } from "@/src/shared/types";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const report = await agentFetch<EvalReport>("/api/v1/admin/evals/golden", {
      method: "POST"
    });
    return NextResponse.json(report);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}
