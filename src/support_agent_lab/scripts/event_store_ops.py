from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from support_agent_lab.config import Settings
from support_agent_lab.memory.event_store import SQLiteEventStore


def _load_event_store(database_url: str | None) -> SQLiteEventStore:
    url = database_url or Settings().app_database_url
    event_store = SQLiteEventStore.from_url(url)
    if event_store is None:
        raise RuntimeError("Only sqlite:/// APP_DATABASE_URL values are supported by this operator command")
    return event_store


def build_parser() -> argparse.ArgumentParser:
    settings = Settings()
    parser = argparse.ArgumentParser(
        description="Operate the SQLite event store used by the support agent service.",
    )
    parser.add_argument(
        "--database-url",
        help="SQLite URL to operate on. Defaults to APP_DATABASE_URL from the environment or .env.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create an online SQLite backup and verify it.")
    backup.add_argument("--output", required=True, help="Path to write the backup database.")
    backup.add_argument("--overwrite", action="store_true", help="Replace the backup file if it already exists.")
    backup.add_argument("--no-verify", action="store_true", help="Skip quick_check verification after backup.")

    restore_drill = subparsers.add_parser(
        "restore-drill",
        help="Copy a backup to a scratch database and prove it can be opened, checked, and queried.",
    )
    restore_drill.add_argument("--backup", required=True, help="Backup database file to drill.")
    restore_drill.add_argument("--tenant-id", default=settings.app_tenant_id, help="Tenant id for high-water checks.")
    restore_drill.add_argument(
        "--restore-output",
        help="Optional path to retain the drilled restore copy. Defaults to a temporary file that is removed.",
    )
    restore_drill.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace --restore-output if it already exists.",
    )

    retention = subparsers.add_parser("retention", help="Preview or apply the configured retention policy.")
    retention.add_argument("--tenant-id", default=settings.app_tenant_id, help="Tenant id to operate on.")
    retention.add_argument("--apply", action="store_true", help="Delete matching rows. Without this flag, dry-run only.")
    retention.add_argument("--include-events", action="store_true", help="Also delete old append-only event rows.")
    retention.add_argument("--vacuum", action="store_true", help="Run VACUUM after an applied deletion.")
    retention.add_argument("--event-retention-days", type=int, default=settings.app_event_retention_days)
    retention.add_argument("--tool-audit-retention-days", type=int, default=settings.app_tool_audit_retention_days)
    retention.add_argument("--idempotency-retention-days", type=int, default=settings.app_idempotency_retention_days)
    retention.add_argument(
        "--alert-delivery-retention-days",
        type=int,
        default=settings.app_alert_delivery_retention_days,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event_store = _load_event_store(args.database_url)
        if args.command == "backup":
            report = event_store.backup_to(
                Path(args.output),
                overwrite=args.overwrite,
                verify=not args.no_verify,
            )
        elif args.command == "restore-drill":
            report = event_store.restore_drill(
                Path(args.backup),
                restore_path=Path(args.restore_output) if args.restore_output else None,
                overwrite=args.overwrite,
                tenant_id=args.tenant_id,
            )
        else:
            report = event_store.apply_retention_policy(
                tenant_id=args.tenant_id,
                dry_run=not args.apply,
                include_events=args.include_events,
                vacuum=args.vacuum,
                event_retention_days=args.event_retention_days,
                tool_audit_retention_days=args.tool_audit_retention_days,
                idempotency_retention_days=args.idempotency_retention_days,
                alert_delivery_retention_days=args.alert_delivery_retention_days,
            )
    except Exception as exc:
        print(f"event store operation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
