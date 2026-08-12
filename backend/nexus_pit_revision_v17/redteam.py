"""Future-leakage redteam attacks for V17-D PIT revision control."""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_pit_revision_v17.fixtures import DAY, T0, build_revision_catalog
from backend.nexus_pit_revision_v17.hard_bans import (
    FutureLeakageError,
    MissingAsKnownAtError,
    TodayRevisionForPastBacktestError,
    UnavailableAtTimeError,
)
from backend.nexus_pit_revision_v17.store import PitRevisionStore, research_query
from backend.nexus_pit_revision_v17.types import DualTimeStamp, ResearchQuery, RevisionRecord


def _fresh_store() -> PitRevisionStore:
    store = PitRevisionStore()
    store.ingest_many(build_revision_catalog())
    return store


def _attack(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = fn()
        blocked = bool(result.get("blocked"))
        survivor = not blocked
        return {
            "attack_id": name,
            "blocked": blocked,
            "survivor": survivor,
            "detail": result.get("detail", ""),
            "status": result.get("status"),
        }
    except Exception as exc:  # noqa: BLE001 — redteam harness captures unexpected leaks
        return {
            "attack_id": name,
            "blocked": False,
            "survivor": True,
            "detail": f"UNEXPECTED_EXCEPTION:{type(exc).__name__}:{exc}",
            "status": "ERROR",
        }


def run_future_leakage_redteam() -> dict[str, Any]:
    """Every attack must be blocked; survivor_count must be 0 for PASS."""
    store = _fresh_store()
    past_aka = T0 + 3 * DAY  # after R1, before R2/R3
    mid_aka = T0 + 6 * DAY  # after R2, before today R3
    findings: list[dict[str, Any]] = []

    # 1) Missing AS_KNOWN_AT must refuse
    def a_missing() -> dict[str, Any]:
        try:
            research_query(store, {"series_id": "SYNTH.BTCUSDT.CLOSE"})  # type: ignore[arg-type]
            return {"blocked": False, "detail": "accepted without as_known_at"}
        except MissingAsKnownAtError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED_MISSING_AS_KNOWN_AT"}

    findings.append(_attack("missing_as_known_at", a_missing))

    # 2) Explicit None AS_KNOWN_AT
    def a_none() -> dict[str, Any]:
        try:
            research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=None)
            return {"blocked": False, "detail": "accepted as_known_at=None"}
        except MissingAsKnownAtError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED_MISSING_AS_KNOWN_AT"}

    findings.append(_attack("null_as_known_at", a_none))

    # 3) Using today's tip revision for past backtest (allow_latest_revision=True)
    def a_today() -> dict[str, Any]:
        try:
            research_query(
                store,
                ResearchQuery(
                    series_id="SYNTH.BTCUSDT.CLOSE",
                    as_known_at=past_aka,
                    allow_latest_revision=True,
                ),
            )
            return {"blocked": False, "detail": "allowed today revision for past backtest"}
        except TodayRevisionForPastBacktestError as exc:
            return {
                "blocked": True,
                "detail": str(exc),
                "status": "REJECTED_TODAY_REVISION_FOR_PAST_BACKTEST",
            }

    findings.append(_attack("today_revision_for_past_backtest", a_today))

    # 4) Honest past query must NOT return R3 (today) or R2
    def a_past_value() -> dict[str, Any]:
        result = research_query(
            store,
            series_id="SYNTH.BTCUSDT.CLOSE",
            as_known_at=past_aka,
        )
        ok = (
            result.status == "AVAILABLE"
            and result.revision_id == "OBS_BTC_CLOSE_R1"
            and result.value == 42000.0
            and result.revision_id != "OBS_BTC_CLOSE_R3_TODAY"
        )
        return {
            "blocked": ok,
            "detail": f"got revision={result.revision_id} value={result.value}",
            "status": result.status,
        }

    findings.append(_attack("past_query_excludes_later_revisions", a_past_value))

    # 5) Mid query sees R2 but not today R3
    def a_mid() -> dict[str, Any]:
        result = research_query(
            store,
            series_id="SYNTH.BTCUSDT.CLOSE",
            as_known_at=mid_aka,
        )
        ok = result.revision_id == "OBS_BTC_CLOSE_R2" and result.value == 41950.0
        return {
            "blocked": ok,
            "detail": f"got revision={result.revision_id}",
            "status": result.status,
        }

    findings.append(_attack("mid_query_sees_r2_not_r3", a_mid))

    # 6) Late-arriving unavailable before available_time
    def a_late() -> dict[str, Any]:
        result = research_query(
            store,
            series_id="SYNTH.ETHUSDT.CLOSE",
            as_known_at=T0 + 4 * DAY,  # before available_time day 7
        )
        ok = result.status == "UNAVAILABLE_AT_TIME" and result.value is None
        return {
            "blocked": ok,
            "detail": f"status={result.status} value={result.value}",
            "status": result.status,
        }

    findings.append(_attack("late_arriving_unavailable_before_available_time", a_late))

    # 7) Backfill unavailable before publish
    def a_backfill() -> dict[str, Any]:
        result = research_query(
            store,
            series_id="SYNTH.SOLUSDT.CLOSE",
            as_known_at=T0 + 5 * DAY,  # backfill at day 10
        )
        ok = result.status == "UNAVAILABLE_AT_TIME"
        return {"blocked": ok, "detail": f"status={result.status}", "status": result.status}

    findings.append(_attack("backfill_unavailable_before_publish", a_backfill))

    # 8) Label revision: early aka sees R1, not corrected R2
    def a_label() -> dict[str, Any]:
        early = research_query(
            store,
            series_id="SYNTH.BTCUSDT.REGIME_LABEL",
            as_known_at=T0 + 5 * DAY,
            label_name="regime_v1",
        )
        late = research_query(
            store,
            series_id="SYNTH.BTCUSDT.REGIME_LABEL",
            as_known_at=T0 + 15 * DAY,
            label_name="regime_v1",
        )
        ok = (
            early.revision_id == "LABEL_REGIME_R1"
            and early.value == "TREND_UP"
            and late.revision_id == "LABEL_REGIME_R2"
            and late.value == "RANGE"
        )
        return {
            "blocked": ok,
            "detail": f"early={early.revision_id}/{early.value} late={late.revision_id}/{late.value}",
            "status": "LABEL_REVISION_OK" if ok else "LABEL_LEAK",
        }

    findings.append(_attack("label_revision_lineage_as_known_at", a_label))

    # 9) Force-inject future revision into selection path
    def a_inject() -> dict[str, Any]:
        from backend.nexus_pit_revision_v17.store import assert_no_future_axes

        future = RevisionRecord(
            revision_id="INJECT_FUTURE",
            series_id="SYNTH.BTCUSDT.CLOSE",
            kind="OBSERVATION",
            value=99999.0,
            times=DualTimeStamp(
                event_time=T0,
                available_time=T0 + 1 * DAY,
                revision_time=T0 + 100 * DAY,
                ingest_time=T0 + 100 * DAY,
            ),
        )
        try:
            assert_no_future_axes(future, as_known_at=past_aka)
            return {"blocked": False, "detail": "future axes accepted"}
        except FutureLeakageError as exc:
            return {"blocked": True, "detail": str(exc), "status": "REJECTED_FUTURE_LEAKAGE"}

    findings.append(_attack("inject_future_revision_axes", a_inject))

    # 10) Unavailable silent-fill raise path
    def a_silent() -> dict[str, Any]:
        try:
            research_query(
                store,
                series_id="SYNTH.DOES.NOT.EXIST",
                as_known_at=past_aka,
                raise_on_unavailable=True,
            )
            return {"blocked": False, "detail": "silent fill allowed"}
        except UnavailableAtTimeError as exc:
            return {"blocked": True, "detail": str(exc), "status": "UNAVAILABLE_AT_TIME"}

    findings.append(_attack("unavailable_at_time_no_silent_fill", a_silent))

    # 11) Lineage must not include future parents/children beyond aka
    def a_lineage() -> dict[str, Any]:
        result = research_query(
            store,
            series_id="SYNTH.BTCUSDT.CLOSE",
            as_known_at=mid_aka,
        )
        ids = [row["revision_id"] for row in result.lineage]
        ok = (
            "OBS_BTC_CLOSE_R1" in ids
            and "OBS_BTC_CLOSE_R2" in ids
            and "OBS_BTC_CLOSE_R3_TODAY" not in ids
        )
        return {
            "blocked": ok,
            "detail": f"lineage_ids={ids}",
            "status": result.status,
        }

    findings.append(_attack("revision_lineage_truncated_at_as_known_at", a_lineage))

    # 12) Event-time alone must not unlock unavailable data
    def a_event_only() -> dict[str, Any]:
        result = research_query(
            store,
            series_id="SYNTH.ETHUSDT.CLOSE",
            as_known_at=T0 + 3 * DAY,  # after event_time day 2, before available day 7
            event_time=T0 + 2 * DAY,
        )
        ok = result.status == "UNAVAILABLE_AT_TIME"
        return {"blocked": ok, "detail": f"status={result.status}", "status": result.status}

    findings.append(_attack("event_time_alone_does_not_unlock", a_event_only))

    survivors = [f for f in findings if f.get("survivor")]
    return {
        "schema": "v17_d_future_leakage_redteam_v1",
        "attack_count": len(findings),
        "blocked_count": sum(1 for f in findings if f.get("blocked")),
        "survivor_count": len(survivors),
        "survivors": [f["attack_id"] for f in survivors],
        "findings": findings,
        "pass": len(survivors) == 0,
    }
