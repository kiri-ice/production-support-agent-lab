from __future__ import annotations

from collections import Counter

import httpx

from support_agent_lab.config import Settings
from support_agent_lab.memory.event_store import SQLiteEventStore
from support_agent_lab.monitoring.alert_dispatcher import (
    AlertDispatchReport,
    dispatch_alert_deliveries,
    enqueue_alert_deliveries,
)
from support_agent_lab.monitoring.monitor import MonitorAlert, summarize_monitor_events


def monitor_alert_webhook_url(settings: Settings) -> str | None:
    if not settings.app_monitor_alert_webhook_enabled:
        return None
    return settings.app_monitor_alert_webhook_url


def load_event_store_alerts(
    *,
    event_store: SQLiteEventStore,
    settings: Settings,
    monitor_limit: int,
) -> list[MonitorAlert]:
    events = event_store.list_monitor_events(
        tenant_id=settings.app_tenant_id,
        limit=monitor_limit,
        order="desc",
    )
    triage_events = event_store.list_monitor_alert_triage_events(
        tenant_id=settings.app_tenant_id,
        limit=monitor_limit,
    )
    return summarize_monitor_events(events, triage_events=triage_events).alerts


def run_alert_delivery_cycle(
    *,
    settings: Settings,
    event_store: SQLiteEventStore,
    alerts: list[MonitorAlert] | None = None,
    monitor_limit: int = 500,
    dispatch_limit: int = 25,
    worker_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> AlertDispatchReport:
    active_alerts = alerts
    if active_alerts is None:
        active_alerts = load_event_store_alerts(
            event_store=event_store,
            settings=settings,
            monitor_limit=monitor_limit,
        )
    webhook_url = monitor_alert_webhook_url(settings)
    if not webhook_url:
        return AlertDispatchReport(
            webhook_enabled=False,
            skipped_count=len(active_alerts),
        )
    enqueue_report = enqueue_alert_deliveries(
        event_store=event_store,
        tenant_id=settings.app_tenant_id,
        alerts=active_alerts,
        webhook_url=webhook_url,
        min_severity=settings.app_monitor_alert_min_severity,
    )
    dispatch_report = dispatch_alert_deliveries(
        event_store=event_store,
        tenant_id=settings.app_tenant_id,
        webhook_url=webhook_url,
        webhook_secret=settings.app_monitor_alert_webhook_secret,
        max_attempts=settings.app_monitor_alert_max_attempts,
        limit=dispatch_limit,
        timeout_ms=settings.app_monitor_alert_webhook_timeout_ms,
        backoff_base_seconds=settings.app_monitor_alert_backoff_base_seconds,
        backoff_max_seconds=settings.app_monitor_alert_backoff_max_seconds,
        claim_lease_seconds=settings.app_monitor_alert_claim_lease_seconds,
        worker_id=worker_id,
        transport=transport,
    )
    return AlertDispatchReport(
        webhook_enabled=True,
        enqueued_count=enqueue_report.enqueued_count,
        existing_count=enqueue_report.existing_count,
        skipped_count=enqueue_report.skipped_count + dispatch_report.skipped_count,
        claimed_count=dispatch_report.claimed_count,
        attempted_count=dispatch_report.attempted_count,
        sent_count=dispatch_report.sent_count,
        failed_count=dispatch_report.failed_count,
        dead_count=dispatch_report.dead_count,
        deliveries=[*enqueue_report.deliveries, *dispatch_report.deliveries],
    )


def summarize_dispatch_report(report: AlertDispatchReport) -> dict[str, object]:
    statuses = Counter(record.status.value for record in report.deliveries)
    return {
        "webhook_enabled": report.webhook_enabled,
        "enqueued_count": report.enqueued_count,
        "existing_count": report.existing_count,
        "skipped_count": report.skipped_count,
        "claimed_count": report.claimed_count,
        "attempted_count": report.attempted_count,
        "sent_count": report.sent_count,
        "failed_count": report.failed_count,
        "dead_count": report.dead_count,
        "delivery_count": len(report.deliveries),
        "delivery_ids": [record.id for record in report.deliveries],
        "delivery_status_counts": dict(sorted(statuses.items())),
    }
