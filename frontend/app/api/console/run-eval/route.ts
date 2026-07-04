import { NextRequest, NextResponse } from "next/server";
import { agentFetch, issueFrom } from "@/src/server/agentApi";
import type { EvalCaseResult, EvalGateCaseSummary, EvalGateRecord, EvalReport, JsonRecord } from "@/src/shared/types";

export const dynamic = "force-dynamic";

type EvalGateRunResponse = {
  gate_name: string;
  gate_run_id: string;
  status: "passed" | "failed" | "error";
  total: number;
  passed: number;
  score: number;
  records: EvalGateRecord[];
};

export async function POST(request: NextRequest) {
  try {
    const parsed = await request.json().catch(() => ({}));
    const body: JsonRecord =
      typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
        ? (parsed as JsonRecord)
        : {};
    const gate = await agentFetch<EvalGateRunResponse>("/api/v1/admin/evals/staging", {
      method: "POST",
      body
    });
    return NextResponse.json(toEvalReport(gate));
  } catch (error) {
    const issue = issueFrom(error);
    return NextResponse.json({ detail: issue.detail }, { status: issue.status });
  }
}

function toEvalReport(gate: EvalGateRunResponse): EvalReport {
  const records = gate.records.filter((record) => record.runner !== "aggregate");
  return {
    total: gate.total,
    passed: gate.passed,
    score: gate.score,
    results: records.flatMap((record) => {
      if (record.case_results.length) {
        return record.case_results.map((result) => fromGateCase(record, result));
      }
      if (record.status === "passed") {
        return [];
      }
      return [
        fromGateCase(record, {
          case_id: `${record.suite_id}:runner`,
          passed: false,
          score: record.score ?? 0,
          failures: [record.error_message ?? (record.failed_case_ids.join(", ") || "Eval suite failed.")],
          observed_intent: record.runner,
          observed_route: null,
          observed_error_codes: [],
          observed_policy_codes: []
        })
      ];
    })
  };
}

function fromGateCase(record: EvalGateRecord, result: EvalGateCaseSummary): EvalCaseResult {
  return {
    case_id: `${record.suite_id}:${result.case_id}`,
    passed: result.passed,
    score: result.score,
    failures: result.failures,
    observed_intent: result.observed_intent,
    observed_confidence: null,
    observed_route: result.observed_route,
    observed_route_needs_human: null,
    observed_tools: [],
    observed_error_codes: result.observed_error_codes,
    observed_policy_codes: result.observed_policy_codes,
    answer: ""
  };
}
