"""Expanded future-leakage redteam — NEW attacks beyond base V17-D twelve."""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_pit_revision_v17.fixtures import DAY, T0, build_revision_catalog
from backend.nexus_pit_revision_v17.hard_bans import (
    FutureLeakageError,
    MissingAsKnownAtError,
    TodayRevisionForPastBacktestError,
    UnavailableAtTimeError,
)
from backend.nexus_pit_revision_v17.redteam import run_future_leakage_redteam
from backend.nexus_pit_revision_v17.store import PitRevisionStore, assert_no_future_axes, research_query
from backend.nexus_pit_revision_v17.types import DualTimeStamp, ResearchQuery, RevisionRecord


def _fresh_store() -> PitRevisionStore:
    store = PitRevisionStore()
    store.ingest_many(build_revision_catalog())
    return store


def _wrap(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = fn()
        blocked = bool(result.get("blocked"))
        return {
            "attack_id": name,
            "blocked": blocked,
            "survivor": not blocked,
            "detail": result.get("detail", ""),
            "status": result.get("status"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "attack_id": name,
            "blocked": False,
            "survivor": True,
            "detail": f"UNEXPECTED:{type(exc).__name__}:{exc}",
            "status": "ERROR",
        }


def run_expanded_future_leakage_redteam() -> dict[str, Any]:
    """Additional future-leakage attacks; survivors must remain 0 (including base)."""
    store = _fresh_store()
    past_aka = T0 + 3 * DAY
    findings: list[dict[str, Any]] = []

    def a_negative() -> dict[str, Any]:
        try:
            research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=-100)
            return {"blocked": False, "detail": "accepted_negative_aka"}
        except MissingAsKnownAtError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED"}

    findings.append(_wrap("expand_negative_as_known_at", a_negative))

    def a_zero() -> dict[str, Any]:
        try:
            research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=0)
            return {"blocked": False, "detail": "accepted_zero_aka"}
        except MissingAsKnownAtError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED"}

    findings.append(_wrap("expand_zero_as_known_at", a_zero))

    def a_empty_dict() -> dict[str, Any]:
        try:
            research_query(store, {"series_id": "SYNTH.BTCUSDT.CLOSE", "as_known_at": None})
            return {"blocked": False, "detail": "accepted_none_in_dict"}
        except MissingAsKnownAtError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED"}

    findings.append(_wrap("expand_dict_none_as_known_at", a_empty_dict))

    def a_boundary_before_r2() -> dict[str, Any]:
        # R2 revision_time = T0+5d; aka exactly one ms before must not see R2.
        aka = T0 + 5 * DAY - 1
        result = research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=aka)
        ok = result.revision_id == "OBS_BTC_CLOSE_R1" and result.value == 42000.0
        return {"blocked": ok, "detail": f"revision={result.revision_id}", "status": result.status}

    findings.append(_wrap("expand_boundary_ms_before_r2", a_boundary_before_r2))

    def a_boundary_at_r2() -> dict[str, Any]:
        aka = T0 + 5 * DAY
        result = research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=aka)
        ok = result.revision_id == "OBS_BTC_CLOSE_R2" and result.value == 41950.0
        return {"blocked": ok, "detail": f"revision={result.revision_id}", "status": result.status}

    findings.append(_wrap("expand_boundary_ms_at_r2", a_boundary_at_r2))

    def a_ingest_only_future() -> dict[str, Any]:
        # available+revision known, ingest in future — must be invisible.
        future_ingest = RevisionRecord(
            revision_id="INJECT_FUTURE_INGEST",
            series_id="SYNTH.BTCUSDT.CLOSE",
            kind="OBSERVATION",
            value=1.0,
            times=DualTimeStamp(
                event_time=T0,
                available_time=T0 + DAY,
                revision_time=T0 + DAY,
                ingest_time=past_aka + DAY,
            ),
            parent_revision_id="OBS_BTC_CLOSE_R1",
        )
        try:
            assert_no_future_axes(future_ingest, as_known_at=past_aka)
            return {"blocked": False, "detail": "future_ingest_accepted"}
        except FutureLeakageError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED_FUTURE_LEAKAGE"}

    findings.append(_wrap("expand_future_ingest_axis", a_ingest_only_future))

    def a_label_future_parent_leak() -> dict[str, Any]:
        # Query early label; lineage must not include R2.
        result = research_query(
            store,
            series_id="SYNTH.BTCUSDT.REGIME_LABEL",
            as_known_at=T0 + 5 * DAY,
            label_name="regime_v1",
        )
        ids = [row["revision_id"] for row in result.lineage]
        ok = result.revision_id == "LABEL_REGIME_R1" and "LABEL_REGIME_R2" not in ids
        return {"blocked": ok, "detail": f"lineage={ids}", "status": result.status}

    findings.append(_wrap("expand_label_lineage_no_future_child", a_label_future_parent_leak))

    def a_allow_latest_mid() -> dict[str, Any]:
        try:
            research_query(
                store,
                ResearchQuery(
                    series_id="SYNTH.BTCUSDT.CLOSE",
                    as_known_at=T0 + 6 * DAY,
                    allow_latest_revision=True,
                ),
            )
            return {"blocked": False, "detail": "allow_latest_accepted"}
        except TodayRevisionForPastBacktestError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED"}

    findings.append(_wrap("expand_allow_latest_before_tip", a_allow_latest_mid))

    def a_raise_unavailable() -> dict[str, Any]:
        try:
            research_query(
                store,
                series_id="SYNTH.SOLUSDT.CLOSE",
                as_known_at=T0 + 5 * DAY,
                raise_on_unavailable=True,
            )
            return {"blocked": False, "detail": "silent_or_filled"}
        except UnavailableAtTimeError as exc:
            return {"blocked": True, "detail": str(exc), "status": "UNAVAILABLE_AT_TIME"}

    findings.append(_wrap("expand_backfill_raise_on_unavailable", a_raise_unavailable))

    def a_select_visible_excludes_today() -> dict[str, Any]:
        visible = store.visible_revisions("SYNTH.BTCUSDT.CLOSE", as_known_at=past_aka)
        ids = {r.revision_id for r in visible}
        ok = "OBS_BTC_CLOSE_R1" in ids and "OBS_BTC_CLOSE_R3_TODAY" not in ids and "OBS_BTC_CLOSE_R2" not in ids
        return {"blocked": ok, "detail": f"ids={sorted(ids)}", "status": "VISIBLE_OK" if ok else "LEAK"}

    findings.append(_wrap("expand_visible_set_excludes_future", a_select_visible_excludes_today))

    survivors = [f["attack_id"] for f in findings if f.get("survivor")]
    expanded = {
        "schema": "v17_deep_future_leakage_expand_v1",
        "attack_count": len(findings),
        "blocked_count": sum(1 for f in findings if f.get("blocked")),
        "survivor_count": len(survivors),
        "survivors": survivors,
        "pass": len(survivors) == 0,
        "findings": findings,
    }

    base = run_future_leakage_redteam()
    combined_survivors = list(base.get("survivors") or []) + survivors
    return {
        "schema": "v17_deep_future_leakage_combined_v1",
        "expanded": expanded,
        "base": {
            "attack_count": base["attack_count"],
            "blocked_count": base["blocked_count"],
            "survivor_count": base["survivor_count"],
            "survivors": base.get("survivors") or [],
            "pass": base.get("pass"),
        },
        "attack_count": int(base["attack_count"]) + int(expanded["attack_count"]),
        "blocked_count": int(base["blocked_count"]) + int(expanded["blocked_count"]),
        "survivor_count": len(combined_survivors),
        "survivors": combined_survivors,
        "pass": len(combined_survivors) == 0,
    }
