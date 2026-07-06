from support_agent_lab.tracing import make_traceparent, parse_traceparent


TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


def test_parse_traceparent_accepts_valid_w3c_context():
    parsed = parse_traceparent(f"00-{TRACE_ID}-00f067aa0ba902b7-01")

    assert parsed is not None
    assert parsed.trace_id == TRACE_ID
    assert parsed.parent_id == "00f067aa0ba902b7"
    assert parsed.trace_flags == "01"


def test_parse_traceparent_rejects_unsafe_values():
    assert parse_traceparent(None) is None
    assert parse_traceparent("not-a-traceparent") is None
    assert parse_traceparent(f"ff-{TRACE_ID}-00f067aa0ba902b7-01") is None
    assert parse_traceparent(f"00-{'0' * 32}-00f067aa0ba902b7-01") is None
    assert parse_traceparent(f"00-{TRACE_ID}-{'0' * 16}-01") is None


def test_make_traceparent_returns_standard_context_only_for_valid_trace_id():
    traceparent = make_traceparent(TRACE_ID, span_seed="req:run")

    assert traceparent is not None
    assert traceparent.startswith(f"00-{TRACE_ID}-")
    assert traceparent.endswith("-01")
    assert make_traceparent("gateway_trace_123", span_seed="req:run") is None
