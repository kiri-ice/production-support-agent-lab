import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { FeedbackReviewEvent, FeedbackReviewStatus } from "@/src/shared/types";

export const dynamic = "force-dynamic";

const REVIEW_STATUSES = new Set<FeedbackReviewStatus>([
  "acknowledged",
  "investigating",
  "resolved",
  "dismissed"
]);

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const feedbackId = cleanText(searchParams.get("feedbackId"), 160);
  if (!feedbackId) {
    return NextResponse.json({ detail: "feedbackId is required" }, { status: 400 });
  }
  const limit = clampNumber(searchParams.get("limit"), 1, 200, 100);
  const order = searchParams.get("order") === "desc" ? "desc" : "asc";

  try {
    const reviews = await agentFetch<FeedbackReviewEvent[]>(
      `/api/v1/admin/feedback/${encodeURIComponent(feedbackId)}/reviews`,
      { query: { limit, order } }
    );
    return NextResponse.json(reviews);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const feedbackId = cleanText(readString(body, "feedbackId"), 160);
  const status = readString(body, "status");
  if (!feedbackId) {
    return NextResponse.json({ detail: "feedbackId is required" }, { status: 400 });
  }
  if (!REVIEW_STATUSES.has(status as FeedbackReviewStatus)) {
    return NextResponse.json({ detail: "Invalid feedback review status" }, { status: 400 });
  }

  try {
    const review = await agentFetch<FeedbackReviewEvent>(
      `/api/v1/admin/feedback/${encodeURIComponent(feedbackId)}/reviews`,
      {
        method: "POST",
        body: {
          status,
          assignee_user_id: cleanText(readString(body, "assigneeUserId"), 128) || null,
          note: cleanText(readString(body, "note"), 1000)
        }
      }
    );
    return NextResponse.json(review);
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}

function readString(source: unknown, key: string): string {
  if (!source || typeof source !== "object" || !(key in source)) {
    return "";
  }
  const value = (source as Record<string, unknown>)[key];
  return typeof value === "string" ? value : "";
}

function cleanText(value: string | null, maxLength: number): string {
  return (value ?? "").trim().slice(0, maxLength);
}

function clampNumber(value: string | null, min: number, max: number, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}
