"""Export tool — summary.json, trades.csv, reflections.jsonl, evidence_manifest.json."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.persistence import DemoExecutionPersistence


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
        trades_path = self._export_trades_csv(filters)
        reflections_path = self._export_reflections_jsonl(filters)
        manifest_path = self._export_evidence_manifest(
            filters,
            artifacts=[summary_path, trades_path, reflections_path],
        )
        return {
            "summary": str(summary_path),
            "trades_csv": str(trades_path),
            "reflections_jsonl": str(reflections_path),
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
        summary = {
            "exported_at": time.time(),
            "filters": {
                "from_id": filters.from_id,
                "to_id": filters.to_id,
                "account_epoch": filters.account_epoch,
            },
            "order_count": len(orders),
            "outcome_count": len(outcomes),
            "epoch_count": len(epochs),
            "streams": self.persistence.summary()["stream_counts"],
        }
        path = self.output_dir / "summary.json"
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _export_trades_csv(self, filters: ExportFilters) -> Path:
        orders = self._read_filtered("orders", filters)
        path = self.output_dir / "trades.csv"
        fieldnames = ["order_id", "symbol", "side", "qty", "margin_usdt", "account_epoch", "checksum"]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in orders:
                writer.writerow(row)
        return path

    def _export_reflections_jsonl(self, filters: ExportFilters) -> Path:
        reflections = self._read_filtered("reflections", filters)
        path = self.output_dir / "reflections.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in reflections:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
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
        manifest = {
            "package": "nexus_demo_execution",
            "exported_at": time.time(),
            "filters": {
                "from_id": filters.from_id,
                "to_id": filters.to_id,
                "account_epoch": filters.account_epoch,
            },
            "artifacts": entries,
        }
        path = self.output_dir / "evidence_manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return path
