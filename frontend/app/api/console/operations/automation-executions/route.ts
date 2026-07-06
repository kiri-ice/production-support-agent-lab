import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { OperationsAutomationExecutionRecord } from "@/src/shared/types";

export const dynamic = "force-dynamic";

const STATUSES = new Set(["completed", "failed", "rejected"]);
const SOURCES = new Set(["console", "cron", "on_call_bot", "api"]);

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = request.nextUrl;
    const actionKind = safeString(searchParams.get("action_kind"), 80);
    const actorUserId = safeString(searchParams.get("actor_user_id"), 128);
    const createdAfter = safeString(searchParams.get("created_after"), 64);
    const createdBefore = safeString(searchParams.get("created_before"), 64);
    const status = safeEnum(searchParams.get("status"), STATUSES);
    const source = safeEnum(searchParams.get("source"), SOURCES);
    const limit = clampNumber(searchParams.get("limit"), 1, 500, 50);
    const order = searchParams.get("order") === "asc" ? "asc" : "desc";

    const records = await agentFetch<OperationsAutomationExecutionRecord[]>(
      "/api/v1/admin/operations/automation-executions",
      {
        query: {
          action_kind: actionKind,
          status,
          source,
          actor_user_id: actorUserId,
          created_after: createdAfter,
          created_before: createdBefore,
          limit,
          order
        }
      }
    );
    return NextResponse.json({ records, limit, order });
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}

function safeString(value: string | null, maxLength: number) {
  const trimmed = value?.trim() ?? "";
  return trimmed ? trimmed.slice(0, maxLength) : undefined;
}

function safeEnum(value: string | null, allowed: Set<string>) {
  const trimmed = value?.trim() ?? "";
  return allowed.has(trimmed) ? trimmed : undefined;
}

function clampNumber(value: string | null, min: number, max: number, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(Math.max(Math.trunc(parsed), min), max);
}
