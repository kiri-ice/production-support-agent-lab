import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { SQLiteRestoreDrillReport } from "@/src/shared/types";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json().catch(() => ({}));
    const backupToken = typeof payload.backup_token === "string" ? payload.backup_token : "";
    if (!backupToken) {
      return NextResponse.json(
        { detail: "Verified backup token is required for restore drill." },
        { status: 409 }
      );
    }
    const response = await agentFetch<SQLiteRestoreDrillReport>(
      "/api/v1/admin/event-store/restore-drills",
      {
        method: "POST",
        body: {
          backup_token: backupToken
        }
      }
    );
    return NextResponse.json(response);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}
