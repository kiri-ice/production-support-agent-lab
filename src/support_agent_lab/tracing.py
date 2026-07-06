from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


TRACEPARENT_PATTERN = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-(?P<parent_id>[0-9a-f]{16})-(?P<trace_flags>[0-9a-f]{2})$"
)


@dataclass(frozen=True)
class TraceParent:
    trace_id: str
    parent_id: str
    trace_flags: str


def parse_traceparent(value: str | None) -> TraceParent | None:
    candidate = (value or "").strip().lower()
    match = TRACEPARENT_PATTERN.fullmatch(candidate)
    if not match:
        return None
    if match.group("version") == "ff":
        return None
    trace_id = match.group("trace_id")
    parent_id = match.group("parent_id")
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None
    return TraceParent(
        trace_id=trace_id,
        parent_id=parent_id,
        trace_flags=match.group("trace_flags"),
    )


def make_traceparent(
    trace_id: str | None,
    *,
    span_seed: str,
    trace_flags: str = "01",
) -> str | None:
    normalized_trace_id = (trace_id or "").strip().lower()
    if not _is_valid_trace_id(normalized_trace_id):
        return None
    flags = trace_flags.lower() if re.fullmatch(r"[0-9a-fA-F]{2}", trace_flags) else "01"
    return f"00-{normalized_trace_id}-{_span_id_from_seed(span_seed)}-{flags}"


def _is_valid_trace_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", value)) and value != "0" * 32


def _span_id_from_seed(value: str) -> str:
    span_id = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    if span_id == "0" * 16:
        return "0000000000000001"
    return span_id
