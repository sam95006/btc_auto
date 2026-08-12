"""Export tool — summary.json, account_epochs, snapshots, dry_run_intents, manifest."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.persistence import DemoExecutionPersistence

SECRET_PATTERN = re.compile(
    r"(api[_-]?key|api[_-]?secret|secret|password|token|private[_-]?key)",
    re.I,
)


@dataclass
class ExportFilters:
    from_id: int | None = None
    to_id: int | None = None
    account_epoch: str | None = None


@dataclass
class DemoExecutionExporter:
    persistence: DemoExecutionPersistence
    output_dir: Path

    def export_all(self, filters: ExportFilters | None = None) -> dict[str, Any]:
        filters = filters or ExportFilters()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = self._export_summary(filters)
        epochs_path = self._export_account_epochs(filters)
        snapshots_path = self._export_account_snapshots_csv(filters)
        dry_run_path = self._export_dry_run_intents_jsonl(filters)
        trades_path = self._export_trades_csv(filters)
        reflections_path = self._export_reflections_jsonl(filters)
        protection_path = self._export_protection_checks_jsonl(filters)
        manifest_path = self._export_evidence_manifest(
            filters,
            artifacts=[
                summary_path,
                epochs_path,
                snapshots_path,
                dry_run_path,
                trades_path,
                reflections_path,
                protection_path,
            ],
        )
        return {
            "summary": str(summary_path),
            "account_epochs": str(epochs_path),
            "account_snapshots_csv": str(snapshots_path),
            "dry_run_intents_jsonl": str(dry_run_path),
            "trades_csv": str(trades_path),
            "reflections_jsonl": str(reflections_path),
            "protection_checks_jsonl": str(protection_path),
            "evidence_manifest": str(manifest_path),
        }

    def _read_filtered(self, stream: str, filters: ExportFilters) -> list[dict[str, Any]]:
        return self.persistence.read_all(
            stream,
            account_epoch=filters.account_epoch,
            from_id=filters.from_id,
            to_id=filters.to_id,
        )

    def _export_summary(self, filters: ExportFilters) -> Path:
        orders = self._read_filtered("orders", filters)
        outcomes = self._read_filtered("outcomes", filters)
        epochs = self._read_filtered("epochs", filters)
        intents = self._read_filtered("dry_run_intents", filters)
        summary = redact_record(
            {
                "exported_at": time.time(),
                "filters": {
                    "from_id": filters.from_id,
                    "to_id": filters.to_id,
                    "account_epoch": filters.account_epoch,
                },
                "order_count": len(orders),
                "outcome_count": len(outcomes),
                "epoch_count": len(epochs),
                "dry_run_intent_count": len(intents),
                "streams": self.persistence.summary()["stream_counts"],
            }
        )
        path = self.output_dir / "summary.json"
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _export_account_epochs(self, filters: ExportFilters) -> Path:
        epochs = [redact_record(e) for e in self._read_filtered("epochs", filters)]
        path = self.output_dir / "account_epochs.json"
        path.write_text(json.dumps(epochs, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _export_account_snapshots_csv(self, filters: ExportFilters) -> Path:
        snapshots = self._read_filtered("snapshots", filters)
        path = self.output_dir / "account_snapshots.csv"
        fieldnames = [
            "wallet_balance",
            "equity",
            "available_balance",
            "open_positions",
            "open_orders",
            "source",
            "account_epoch",
            "checksum",
        ]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in snapshots:
                writer.writerow(redact_record(row))
        return path

    def _export_dry_run_intents_jsonl(self, filters: ExportFilters) -> Path:
        intents = self._read_filtered("dry_run_intents", filters)
        path = self.output_dir / "dry_run_intents.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in intents:
                fh.write(json.dumps(redact_record(row), sort_keys=True) + "\n")
        return path

    def _export_trades_csv(self, filters: ExportFilters) -> Path:
        orders = self._read_filtered("orders", filters)
        path = self.output_dir / "trades.csv"
        fieldnames = ["order_id", "symbol", "side", "qty", "margin_usdt", "account_epoch", "checksum"]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in orders:
                writer.writerow(redact_record(row))
        return path

    def _export_reflections_jsonl(self, filters: ExportFilters) -> Path:
        reflections = self._read_filtered("reflections", filters)
        path = self.output_dir / "reflections.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in reflections:
                fh.write(json.dumps(redact_record(row), sort_keys=True) + "\n")
        return path

    def _export_protection_checks_jsonl(self, filters: ExportFilters) -> Path:
        checks = self._read_filtered("protection_checks", filters)
        path = self.output_dir / "protection_checks.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in checks:
                fh.write(json.dumps(redact_record(row), sort_keys=True) + "\n")
        return path

    def _export_evidence_manifest(
        self,
        filters: ExportFilters,
        *,
        artifacts: list[Path],
    ) -> Path:
        entries = []
        for artifact in artifacts:
            data = artifact.read_bytes()
            entries.append(
                {
                    "path": artifact.name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }
            )
        manifest = redact_record(
            {
                "package": "nexus_demo_execution",
                "exported_at": time.time(),
                "filters": {
                    "from_id": filters.from_id,
                    "to_id": filters.to_id,
                    "account_epoch": filters.account_epoch,
                },
                "artifacts": entries,
            }
        )
        path = self.output_dir / "evidence_manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return path


def redact_record(record: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in record.items():
        if SECRET_PATTERN.search(str(key)):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_record(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_record(v) if isinstance(v, dict) else v for v in value
            ]
        else:
            val_str = str(value)
            if SECRET_PATTERN.search(val_str) and len(val_str) > 8:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = value
    return redacted
