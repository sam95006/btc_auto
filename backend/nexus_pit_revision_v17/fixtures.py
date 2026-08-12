"""Synthetic dual-time revision fixtures for V17-D (not live market data)."""
from __future__ import annotations

from typing import Any

from backend.nexus_pit_revision_v17.constants import CONTROL_FIXTURE_LABEL
from backend.nexus_pit_revision_v17.types import DualTimeStamp, RevisionRecord

# Anchor timeline (ms) for deterministic fixtures.
T0 = 1_700_000_000_000  # event day 0
DAY = 86_400_000


def _ts(
    *,
    event_offset_days: int,
    available_offset_days: int,
    revision_offset_days: int,
    ingest_offset_days: int,
) -> DualTimeStamp:
    return DualTimeStamp(
        event_time=T0 + event_offset_days * DAY,
        available_time=T0 + available_offset_days * DAY,
        revision_time=T0 + revision_offset_days * DAY,
        ingest_time=T0 + ingest_offset_days * DAY,
    )


def build_revision_catalog() -> list[RevisionRecord]:
    """Catalog covering as-known-at, later revisions, late-arriving, backfill, labels."""
    records: list[RevisionRecord] = [
        # Initial observation known at T0+1
        RevisionRecord(
            revision_id="OBS_BTC_CLOSE_R1",
            series_id="SYNTH.BTCUSDT.CLOSE",
            kind="OBSERVATION",
            value=42000.0,
            times=_ts(
                event_offset_days=0,
                available_offset_days=1,
                revision_offset_days=1,
                ingest_offset_days=1,
            ),
            parent_revision_id=None,
            notes="initial close print",
            tags=(CONTROL_FIXTURE_LABEL, "initial"),
        ),
        # Later revision correcting the same event (restatement at T0+5)
        RevisionRecord(
            revision_id="OBS_BTC_CLOSE_R2",
            series_id="SYNTH.BTCUSDT.CLOSE",
            kind="OBSERVATION",
            value=41950.0,
            times=_ts(
                event_offset_days=0,
                available_offset_days=1,
                revision_offset_days=5,
                ingest_offset_days=5,
            ),
            parent_revision_id="OBS_BTC_CLOSE_R1",
            notes="exchange restatement / later revision",
            tags=(CONTROL_FIXTURE_LABEL, "later_revision"),
        ),
        # Even later "today" revision (T0+30) — must not leak into past backtests
        RevisionRecord(
            revision_id="OBS_BTC_CLOSE_R3_TODAY",
            series_id="SYNTH.BTCUSDT.CLOSE",
            kind="OBSERVATION",
            value=41880.0,
            times=_ts(
                event_offset_days=0,
                available_offset_days=1,
                revision_offset_days=30,
                ingest_offset_days=30,
            ),
            parent_revision_id="OBS_BTC_CLOSE_R2",
            notes="current tip revision — banned for past as_known_at",
            tags=(CONTROL_FIXTURE_LABEL, "today_revision"),
        ),
        # Late-arriving bar: event at T0+2, only available at T0+7
        RevisionRecord(
            revision_id="OBS_LATE_BAR_R1",
            series_id="SYNTH.ETHUSDT.CLOSE",
            kind="LATE_ARRIVING",
            value=2200.0,
            times=_ts(
                event_offset_days=2,
                available_offset_days=7,
                revision_offset_days=7,
                ingest_offset_days=7,
            ),
            notes="late-arriving exchange feed",
            tags=(CONTROL_FIXTURE_LABEL, "late_arriving"),
        ),
        # Backfill of missing history, published at T0+10
        RevisionRecord(
            revision_id="OBS_BACKFILL_R1",
            series_id="SYNTH.SOLUSDT.CLOSE",
            kind="BACKFILL",
            value=95.5,
            times=_ts(
                event_offset_days=3,
                available_offset_days=10,
                revision_offset_days=10,
                ingest_offset_days=10,
            ),
            notes="historical backfill gap fill",
            tags=(CONTROL_FIXTURE_LABEL, "backfill"),
        ),
        # Label v1 available at T0+4
        RevisionRecord(
            revision_id="LABEL_REGIME_R1",
            series_id="SYNTH.BTCUSDT.REGIME_LABEL",
            kind="LABEL",
            value="TREND_UP",
            times=_ts(
                event_offset_days=0,
                available_offset_days=4,
                revision_offset_days=4,
                ingest_offset_days=4,
            ),
            label_name="regime_v1",
            notes="initial label",
            tags=(CONTROL_FIXTURE_LABEL, "label"),
        ),
        # Label revision at T0+12 (corrected annotation)
        RevisionRecord(
            revision_id="LABEL_REGIME_R2",
            series_id="SYNTH.BTCUSDT.REGIME_LABEL",
            kind="LABEL",
            value="RANGE",
            times=_ts(
                event_offset_days=0,
                available_offset_days=4,
                revision_offset_days=12,
                ingest_offset_days=12,
            ),
            parent_revision_id="LABEL_REGIME_R1",
            label_name="regime_v1",
            notes="label revision / corrected annotation",
            tags=(CONTROL_FIXTURE_LABEL, "label_revision"),
        ),
    ]
    return records


def fixture_summary() -> dict[str, Any]:
    catalog = build_revision_catalog()
    return {
        "schema": "v17_d_fixture_summary",
        "fixture_only": True,
        "real_market_data": False,
        "control_label": CONTROL_FIXTURE_LABEL,
        "record_count": len(catalog),
        "series_ids": sorted({r.series_id for r in catalog}),
        "kinds": sorted({r.kind for r in catalog}),
        "t0_ms": T0,
        "day_ms": DAY,
    }
