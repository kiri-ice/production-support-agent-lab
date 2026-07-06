import json

import httpx
import pytest

from support_agent_lab.config import Settings
from support_agent_lab.memory.event_store import SQLiteEventStore
from support_agent_lab.models import IntentType, MonitorEvent, RiskLevel, utc_now
from support_agent_lab.monitoring.alert_delivery_service import (
    run_alert_delivery_cycle,
    summarize_dispatch_report,
)
from support_agent_lab.monitoring.alert_dispatcher import AlertDispatchReport, build_alert_delivery_record
from support_agent_lab.monitoring.monitor import MonitorAlert
from support_agent_lab.scripts.alert_dispatcher_worker import main as dispatcher_main


WEBHOOK_SECRET = "webhook-signing-secret-with-32-byte-minimum"


def test_alert_delivery_cycle_projects_event_store_alerts_and_sends_once(tmp_path):
    event_store = SQLiteEventStore(tmp_path / "events.db")
    event_store.append_monitor_event(_p1_monitor_event(), tenant_id="demo_tenant")
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(202, json={"ok": True})

    report = run_alert_delivery_cycle(
        settings=_webhook_settings(),
        event_store=event_store,
        monitor_limit=25,
        dispatch_limit=10,
        worker_id="worker-a",
        record_worker_heartbeat=True,
        transport=httpx.MockTransport(handler),
    )
    records = event_store.list_alert_delivery_records(tenant_id="demo_tenant")
    heartbeats = event_store.list_alert_dispatcher_heartbeats(tenant_id="demo_tenant")
    heartbeat_summary = event_store.summarize_alert_dispatcher_heartbeats(
        tenant_id="demo_tenant",
        stale_after_seconds=180,
    )

    assert report.webhook_enabled is True
    assert report.enqueued_count == 1
    assert report.claimed_count == 1
    assert report.attempted_count == 1
    assert report.sent_count == 1
    assert len(calls) == 1
    assert calls[0]["severity"] == "P1"
    assert records[0].status == "sent"
    assert records[0].locked_by is None
    assert records[0].response_status_code == 202
    assert len(heartbeats) == 1
    assert heartbeats[0].worker_id == "worker-a"
    assert heartbeats[0].last_cycle_status == "success"
    assert heartbeats[0].cycle_count == 1
    assert heartbeats[0].sent_count == 1
    assert heartbeat_summary.status == "active"


def test_alert_delivery_cycle_deduplicates_sent_alerts_across_workers(tmp_path):
    event_store = SQLiteEventStore(tmp_path / "events.db")
    event_store.append_monitor_event(_p1_monitor_event(), tenant_id="demo_tenant")
    calls: list[dict] = []
    transport = httpx.MockTransport(lambda request: calls.append(json.loads(request.content)) or httpx.Response(202))

    first = run_alert_delivery_cycle(
        settings=_webhook_settings(),
        event_store=event_store,
        worker_id="worker-a",
        transport=transport,
    )
    second = run_alert_delivery_cycle(
        settings=_webhook_settings(),
        event_store=event_store,
        worker_id="worker-b",
        transport=transport,
    )

    assert first.sent_count == 1
    assert second.enqueued_count == 0
    assert second.existing_count == 1
    assert second.claimed_count == 0
    assert second.attempted_count == 0
    assert len(calls) == 1


def test_alert_delivery_cycle_records_failed_heartbeat(tmp_path, monkeypatch):
    event_store = SQLiteEventStore(tmp_path / "events.db")

    def fail_monitor_read(*args, **kwargs):
        raise RuntimeError("monitor read failed")

    monkeypatch.setattr(event_store, "list_monitor_events", fail_monitor_read)

    with pytest.raises(RuntimeError):
        run_alert_delivery_cycle(
            settings=_webhook_settings(),
            event_store=event_store,
            worker_id="worker-failed",
            record_worker_heartbeat=True,
        )

    heartbeats = event_store.list_alert_dispatcher_heartbeats(tenant_id="demo_tenant")
    assert len(heartbeats) == 1
    assert heartbeats[0].worker_id == "worker-failed"
    assert heartbeats[0].status == "failed"
    assert heartbeats[0].last_cycle_status == "failed"
    assert heartbeats[0].last_error == "RuntimeError"
    assert heartbeats[0].cycle_count == 1


def test_alert_dispatcher_worker_fails_fast_in_production_without_webhook(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_REQUIRE_PRODUCTION", "false")
    monkeypatch.setenv("APP_TENANT_ID", "tenant_prod")
    monkeypatch.setenv("APP_MONITOR_ALERT_WEBHOOK_ENABLED", "false")

    exit_code = dispatcher_main(
        [
            "--once",
            "--json",
            "--database-url",
            f"sqlite:///{tmp_path / 'events.db'}",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "production alert dispatcher requires APP_MONITOR_ALERT_WEBHOOK_ENABLED=true and URL" in captured.err


def test_alert_dispatcher_worker_cli_outputs_sanitized_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_REQUIRE_PRODUCTION", "false")
    monkeypatch.setenv("APP_TENANT_ID", "demo_tenant")

    exit_code = dispatcher_main(
        [
            "--once",
            "--json",
            "--database-url",
            f"sqlite:///{tmp_path / 'events.db'}",
            "--worker-id",
            "dispatcher-cli-private-host",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["webhook_enabled"] is False
    assert "worker_id" not in payload
    assert "worker_id_hash" not in payload
    assert "dispatcher-cli-private-host" not in captured.out


def test_alert_dispatcher_worker_cli_text_omits_worker_id(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_REQUIRE_PRODUCTION", "false")
    monkeypatch.setenv("APP_TENANT_ID", "demo_tenant")

    exit_code = dispatcher_main(
        [
            "--once",
            "--database-url",
            f"sqlite:///{tmp_path / 'events.db'}",
            "--worker-id",
            "dispatcher-text-private-host",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "alert dispatcher cycle" in captured.out
    assert "dispatcher-text-private-host" not in captured.out
    assert "worker=" not in captured.out


def test_alert_dispatcher_json_summary_omits_alert_details():
    alert = MonitorAlert(
        severity="P1",
        key="agent:order:TIMEOUT",
        count=2,
        reason="TIMEOUT clustered across 2 event(s)",
        first_seen_at=utc_now(),
        last_seen_at=utc_now(),
        sample_event_ids=["mon_private"],
        sample_run_ids=["run_private"],
    )
    record = build_alert_delivery_record(
        tenant_id="demo_tenant",
        alert=alert,
        destination_hash="destination_hash_private",
    )
    report = AlertDispatchReport(webhook_enabled=True, enqueued_count=1, deliveries=[record])

    serialized = json.dumps(summarize_dispatch_report(report), ensure_ascii=False)

    assert record.id in serialized
    assert "agent:order:TIMEOUT" not in serialized
    assert "TIMEOUT clustered" not in serialized
    assert "mon_private" not in serialized
    assert "run_private" not in serialized
    assert "destination_hash_private" not in serialized


def _webhook_settings() -> Settings:
    return Settings(
        app_env="local",
        app_monitor_alert_webhook_enabled=True,
        app_monitor_alert_webhook_url="https://hooks.internal.test/alerts",
        app_monitor_alert_webhook_secret=WEBHOOK_SECRET,
    )


def _p1_monitor_event() -> MonitorEvent:
    return MonitorEvent(
        conversation_id="conv_dispatch_worker",
        run_id="run_dispatch_worker",
        timestamp=utc_now(),
        agent_version="agent_test",
        user_intent=IntentType.general_question,
        risk_level=RiskLevel.high,
        grounded=True,
        policy_compliant=False,
        needs_human_review=True,
        failure_types=["PROMPT_INJECTION_ATTEMPT"],
        summary="raw monitor summary should not appear in worker output",
    )
