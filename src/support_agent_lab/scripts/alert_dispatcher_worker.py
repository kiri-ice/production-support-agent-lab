from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from collections.abc import Sequence

from support_agent_lab.config import Settings
from support_agent_lab.memory.event_store import SQLiteEventStore
from support_agent_lab.monitoring.alert_delivery_service import (
    monitor_alert_webhook_url,
    run_alert_delivery_cycle,
    summarize_dispatch_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the durable monitor alert delivery dispatcher.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one dispatch cycle and exit. This is the default.")
    mode.add_argument("--interval-seconds", type=int, help="Run forever with this delay between cycles.")
    parser.add_argument("--database-url", help="SQLite APP_DATABASE_URL override for the alert delivery outbox.")
    parser.add_argument("--monitor-limit", type=int, default=500, help="Monitor events to inspect per cycle.")
    parser.add_argument("--dispatch-limit", type=int, default=25, help="Due delivery rows to claim per cycle.")
    parser.add_argument("--worker-id", help="Stable worker id used for outbox claim leases.")
    parser.add_argument("--json", action="store_true", help="Emit sanitized JSON summaries.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    worker_id = args.worker_id or _default_worker_id()
    try:
        event_store = _load_event_store(args.database_url or settings.app_database_url)
        _validate_worker_config(settings, event_store)
    except Exception as exc:
        _emit_error(str(exc), json_output=args.json)
        return 2

    def run_once() -> None:
        report = run_alert_delivery_cycle(
            settings=settings,
            event_store=event_store,
            monitor_limit=args.monitor_limit,
            dispatch_limit=args.dispatch_limit,
            worker_id=worker_id,
        )
        _emit_report(report, worker_id=worker_id, json_output=args.json)

    if not args.interval_seconds:
        run_once()
        return 0
    if args.interval_seconds < 1:
        _emit_error("--interval-seconds must be >= 1", json_output=args.json)
        return 2
    try:
        while True:
            run_once()
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        return 0


def _load_event_store(database_url: str) -> SQLiteEventStore:
    event_store = SQLiteEventStore.from_url(database_url)
    if event_store is None:
        raise RuntimeError("alert dispatcher requires a sqlite:/// APP_DATABASE_URL")
    return event_store


def _validate_worker_config(settings: Settings, event_store: SQLiteEventStore) -> None:
    if settings.app_require_production and not settings.is_production:
        raise RuntimeError("APP_REQUIRE_PRODUCTION=true requires APP_ENV=production")
    if settings.is_production and event_store is None:
        raise RuntimeError("production alert dispatcher requires a configured event store")
    if settings.is_production and not monitor_alert_webhook_url(settings):
        raise RuntimeError("production alert dispatcher requires APP_MONITOR_ALERT_WEBHOOK_ENABLED=true and URL")
    if settings.is_production and not settings.app_monitor_alert_webhook_secret:
        raise RuntimeError("production alert dispatcher requires APP_MONITOR_ALERT_WEBHOOK_SECRET")


def _emit_report(report, *, worker_id: str, json_output: bool) -> None:
    summary = summarize_dispatch_report(report)
    summary["worker_id"] = worker_id
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return
    print(
        "alert dispatcher cycle "
        f"worker={worker_id} "
        f"webhook_enabled={summary['webhook_enabled']} "
        f"enqueued={summary['enqueued_count']} "
        f"existing={summary['existing_count']} "
        f"claimed={summary['claimed_count']} "
        f"sent={summary['sent_count']} "
        f"failed={summary['failed_count']} "
        f"dead={summary['dead_count']}"
    )


def _emit_error(message: str, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps({"error": message}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return
    print(f"alert dispatcher worker failed: {message}", file=sys.stderr)


def _default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


if __name__ == "__main__":
    raise SystemExit(main())
