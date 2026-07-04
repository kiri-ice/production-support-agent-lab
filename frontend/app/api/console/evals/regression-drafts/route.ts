import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { RegressionDraftRequest, RegressionDraftResponse } from "@/src/shared/types";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as RegressionDraftRequest;
    const draft = await agentFetch<RegressionDraftResponse>("/api/v1/admin/evals/regression-drafts", {
      method: "POST",
      body
    });
    return NextResponse.json(draft);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}
