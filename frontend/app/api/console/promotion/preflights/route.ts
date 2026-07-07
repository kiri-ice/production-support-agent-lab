import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { JsonRecord, PromotionPreflightRecord } from "@/src/shared/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const limit = clampNumber(searchParams.get("limit"), 1, 100, 5);
  const order = searchParams.get("order") === "asc" ? "asc" : "desc";

  try {
    const preflights = await agentFetch<PromotionPreflightRecord[]>("/api/v1/admin/promotion/preflights", {
      query: { limit, order }
    });
    return NextResponse.json(preflights);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json().catch(() => ({}));
    const body = promotionPreflightPayload(payload);
    const preflight = await agentFetch<PromotionPreflightRecord>("/api/v1/admin/promotion/preflights", {
      method: "POST",
      body
    });
    return NextResponse.json(preflight);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}

function promotionPreflightPayload(payload: unknown): JsonRecord {
  const source = asRecord(payload);
  return {
    target_version: stringValue(source.target_version, 128),
    source: source.source === "live" ? "live" : "event_store",
    deep: true,
    ops: true,
    window_hours: clampNumber(source.window_hours, 1, 168, 24),
    max_active_p0p1_alerts: clampNumber(source.max_active_p0p1_alerts, 0, 100, 0),
    max_active_alerts: clampNumber(source.max_active_alerts, 0, 1000, 10),
    max_tool_failure_rate: clampNumber(source.max_tool_failure_rate, 0, 1, 0.05),
    max_feedback_negative_rate: clampNumber(source.max_feedback_negative_rate, 0, 1, 0.4),
    max_eval_age_hours: clampNumber(source.max_eval_age_hours, 1, 720, 24),
    min_tool_calls: clampNumber(source.min_tool_calls, 0, 10000, 1),
    min_feedback_count: clampNumber(source.min_feedback_count, 0, 10000, 5),
    expires_in_minutes: clampNumber(source.expires_in_minutes, 1, 240, 30)
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown, maxLength: number): string {
  return typeof value === "string" ? value.slice(0, maxLength) : "";
}

function clampNumber(value: unknown, min: number, max: number, fallback: number) {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}
