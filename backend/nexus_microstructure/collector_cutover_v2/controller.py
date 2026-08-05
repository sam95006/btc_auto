"""Collector Cutover V2 controller — synthetic/public-readonly proof orchestration."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.clock_guard import ClockRollbackRejected
from backend.nexus_microstructure.collector_cutover_v2.constants import (
    EVENT_STUDY_STATUS,
    R2_HIGH_DISPOSITIONS,
    REFERENCE_CAMPAIGN_ID,
    RETAINED_CLASSIFICATION_COUNTS,
    RETAINED_PRIMARY_CLASSIFICATION_COUNTS,
    SCHEMA,
)
from backend.nexus_microstructure.collector_cutover_v2.finalizer_v2_compat import FinalizerV2Compat
from backend.nexus_microstructure.collector_cutover_v2.migration_guard import (
    OpenPartitionMigrationBlocked,
    assert_migration_safe,
    migration_dry_run,
)
from backend.nexus_microstructure.collector_cutover_v2.open_tail_seal import open_tail_seal_policy
from backend.nexus_microstructure.collector_cutover_v2.storage_controller import StorageControllerV2
from backend.nexus_microstructure.collector_cutover_v2.writer_v2 import DurablePartitionWriterV2
from backend.nexus_microstructure.event_study_hard_block_v11_1 import event_study_gate
from backend.nexus_microstructure.integrity_recovery_v11.classify import (
    classify_campaign_partitions,
    discover_partitions_v11,
)
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import PartitionIdentityConflict


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public_readonly_tick(symbol: str, ts_ms: int, seq: int) -> dict[str, Any]:
    """Synthetic event shaped like read-only public trade-tick fields (no live exchange)."""
    return {
        "source": "public_readonly_fixture",
        "family": "AGGRESSIVE_TRADE_FLOW",
        "symbol": symbol,
        "exchange_timestamp": ts_ms,
        "receive_wall_timestamp": ts_ms + 2,
        "seq": seq,
        "price": "100.0",
        "size": "0.01",
        "side": "Buy",
    }


class CollectorCutoverControllerV2:
    """Run cutover proofs under an isolated root; never touches prior raw campaigns."""

    def __init__(self, repo_root: Path, *, work_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.work_root = Path(work_root)
        self.work_root.mkdir(parents=True, exist_ok=True)

    def run_synthetic_proofs(self) -> dict[str, Any]:
        base = 1_754_265_600_000  # fixed synthetic epoch
        scenarios: dict[str, Any] = {}

        # --- exclusive partition IDs (R2-D-001) ---
        root_excl = self.work_root / "exclusive"
        w1 = DurablePartitionWriterV2(
            root_excl,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="BTCUSDT",
            capture_session_id="cutover_excl",
            buffer_max_events=1,
            flush_interval_s=0.01,
        )
        w2 = DurablePartitionWriterV2(
            root_excl,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="BTCUSDT",
            capture_session_id="cutover_excl",
            buffer_max_events=1,
            flush_interval_s=0.01,
        )
        w1.accept(_public_readonly_tick("BTCUSDT", base, 1))
        conflicted = False
        try:
            w2.accept(_public_readonly_tick("BTCUSDT", base + 1, 2))
        except PartitionIdentityConflict:
            conflicted = True
        close1 = w1.close()
        try:
            w2.close()
        except Exception:  # noqa: BLE001
            pass
        scenarios["exclusive_partition_ids"] = {
            "status": "FIXED" if conflicted and len(list(root_excl.rglob("*.jsonl.gz"))) == 1 else "FAIL",
            "conflict_raised": conflicted,
            "r2": "R2-D-001",
            "writer_close": {
                "manifest_complete": close1.get("manifest_complete"),
                "atomic_manifest_seal": close1.get("atomic_manifest_seal"),
            },
        }

        # --- atomic manifest seal + open-tail kill ---
        root_seal = self.work_root / "seal"
        ws = DurablePartitionWriterV2(
            root_seal,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="ETHUSDT",
            capture_session_id="cutover_seal",
            buffer_max_events=1,
            flush_interval_s=0.01,
        )
        for i in range(5):
            ws.accept(_public_readonly_tick("ETHUSDT", base + i * 1000, i))
        sealed = ws.close()
        open_left = list(root_seal.rglob("*.jsonl.gz.open"))
        scenarios["atomic_manifest_seal"] = {
            "status": "FIXED"
            if sealed.get("manifest_complete") and sealed.get("atomic_manifest_seal") and not open_left
            else "FAIL",
            "open_markers_remaining": len(open_left),
            "partitions": len(sealed.get("partitions") or []),
        }

        root_kill = self.work_root / "kill"
        wk = DurablePartitionWriterV2(
            root_kill,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="SOLUSDT",
            capture_session_id="cutover_kill",
            buffer_max_events=1,
            flush_interval_s=0.01,
        )
        for i in range(4):
            wk.accept(_public_readonly_tick("SOLUSDT", base + i * 1000, i))
        abandoned = wk.abandon_open_without_finalize()
        parts_k = discover_partitions_v11(root_kill)
        clf_k = classify_campaign_partitions(parts_k)
        scenarios["open_tail_on_kill"] = {
            "status": "PASS"
            if abandoned and parts_k and (parts_k[0].get("is_open_tail") or parts_k[0].get("open_marker_present"))
            else "FAIL",
            "abandoned": str(abandoned) if abandoned else None,
            "classifications": clf_k.get("classification_counts"),
        }

        # --- persistent clock guard (R2-D-003) ---
        root_clock = self.work_root / "clock"
        meta = root_clock / "_session_meta" / "cutover_clock"
        wc = DurablePartitionWriterV2(
            root_clock,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="BTCUSDT",
            capture_session_id="cutover_clock",
            buffer_max_events=1,
            flush_interval_s=0.01,
            session_meta_dir=meta,
        )
        wc.accept(_public_readonly_tick("BTCUSDT", base + 3_600_000, 1))  # hour+1
        wc.close()
        # Reopen new writer sharing meta — must load watermark and reject rollback.
        wc2 = DurablePartitionWriterV2(
            root_clock,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="BTCUSDT",
            capture_session_id="cutover_clock",
            buffer_max_events=1,
            flush_interval_s=0.01,
            session_meta_dir=meta,
        )
        rejected = False
        try:
            wc2.accept(_public_readonly_tick("BTCUSDT", base, 2))  # prior hour
        except ClockRollbackRejected:
            rejected = True
        # With resume boundary, allow once.
        wc2.arm_resume_boundary()
        resumed_ok = False
        try:
            wc2.accept(_public_readonly_tick("BTCUSDT", base + 1000, 3))
            resumed_ok = True
        except ClockRollbackRejected:
            resumed_ok = False
        wc2.close()
        scenarios["persistent_clock_guard"] = {
            "status": "FIXED" if rejected and resumed_ok else "FAIL",
            "rollback_rejected_without_resume": rejected,
            "resume_boundary_allows_discontinuity": resumed_ok,
            "r2": "R2-D-003",
            "watermark_persistent": True,
        }

        # --- resume-safe linkage ---
        root_link = self.work_root / "linkage"
        wl = DurablePartitionWriterV2(
            root_link,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="BTCUSDT",
            capture_session_id="cutover_link",
            buffer_max_events=1,
            flush_interval_s=0.01,
        )
        for i in range(3):
            wl.accept(_public_readonly_tick("BTCUSDT", base + i * 1000, i))
        wl.close()
        parts_l = discover_partitions_v11(root_link)
        audit = wl.linkage.audit(parts_l)
        scenarios["resume_safe_linkage"] = {
            "status": "PASS" if audit.get("cross_partition_linkage_status") == "PASS" else "FAIL",
            "linkage_breaks": audit.get("linkage_breaks"),
            "last_sealed": wl.linkage.last_sealed_partition_id,
        }

        # --- migration guard (R2-D-005) ---
        root_mig = self.work_root / "migration"
        wm = DurablePartitionWriterV2(
            root_mig,
            exchange="PUBLIC",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="BTCUSDT",
            capture_session_id="cutover_mig",
            buffer_max_events=1,
            flush_interval_s=0.01,
        )
        wm.accept(_public_readonly_tick("BTCUSDT", base, 1))
        wm.abandon_open_without_finalize()
        blocked = False
        try:
            assert_migration_safe(root_mig)
        except OpenPartitionMigrationBlocked:
            blocked = True
        dry = migration_dry_run(root_mig)
        scenarios["migration_open_partition_guard"] = {
            "status": "FIXED" if blocked and dry.get("would_block") else "FAIL",
            "blocked": blocked,
            "r2": "R2-D-005",
            "dry_run": dry,
        }

        # --- storage controller + automatic safe stop ---
        storage = StorageControllerV2(partitions_root=root_seal, hard_limit_bytes=500, soft_limit_bytes=200)
        storage.observe_write(compressed_delta=300)
        storage.observe_write(compressed_delta=300)
        ctl = storage.evaluate(previous_campaign_finalized=True)
        scenarios["storage_controller_safe_stop"] = {
            "status": "PASS" if ctl.get("safe_stop_required") else "FAIL",
            "safe_stop_required": ctl.get("safe_stop_required"),
            "reasons": (ctl.get("automatic_safe_stop") or {}).get("reasons"),
            "report": ctl,
        }

        # --- Finalizer V2 compat ---
        compat = FinalizerV2Compat(self.repo_root)
        envelope = compat.build_envelope(
            cutover_writer_report=sealed,
            linkage_audit=audit,
            storage_controller=ctl,
        )
        scenarios["finalizer_v2_compat"] = {
            "status": "PASS"
            if envelope.get("event_study_readiness_status") == EVENT_STUDY_STATUS
            and envelope["retained_classifications"]["raw_modified"] is False
            and envelope["retained_classifications"]["classification_counts"]["EXPECTED_OPEN_TAIL"] == 113
            and envelope["retained_classifications"]["classification_counts"]["ACTUAL_DATA_CORRUPTION"] == 0
            else "FAIL",
            "event_study": envelope.get("event_study_readiness_status"),
            "raw_modified": envelope["retained_classifications"]["raw_modified"],
        }

        all_ok = all(
            s.get("status") in {"FIXED", "PASS"} for s in scenarios.values()
        )
        return {
            "schema": f"{SCHEMA}_synthetic_proofs",
            "created_at": _utc(),
            "all_passed": all_ok,
            "scenarios": scenarios,
            "open_tail_seal_policy": open_tail_seal_policy(),
            "finalizer_v2_envelope": envelope,
            "r2_high_dispositions": dict(R2_HIGH_DISPOSITIONS),
            "retained_classifications": {
                "raw_modified": False,
                "classification_counts": dict(RETAINED_CLASSIFICATION_COUNTS),
                "primary_classification_counts": dict(RETAINED_PRIMARY_CLASSIFICATION_COUNTS),
                "campaign_id": REFERENCE_CAMPAIGN_ID,
            },
            "event_study_gate": event_study_gate(),
            "event_study_readiness_status": EVENT_STUDY_STATUS,
            "event_study_real_execution": False,
            "live_capture_started": False,
            "exchange_write_attempt_count": 0,
            "demo_used": False,
            "mainnet_used": False,
        }
