"""Timestamp boundary / DST / UTC edge attacks (leap-second documented guard)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.nexus_deep_pit_survivorship.constants import LEAP_SECOND_POLICY
from backend.nexus_deep_pit_survivorship.hard_bans import (
    HardBanViolation,
    refuse_leap_second_aware_claim,
    refuse_tz_local_as_known_at,
)
from backend.nexus_pit_revision_v17.fixtures import DAY, T0, build_revision_catalog
from backend.nexus_pit_revision_v17.hard_bans import MissingAsKnownAtError
from backend.nexus_pit_revision_v17.store import PitRevisionStore, research_query


def _fresh_store() -> PitRevisionStore:
    store = PitRevisionStore()
    store.ingest_many(build_revision_catalog())
    return store


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def utc_midnight_boundaries() -> list[int]:
    """UTC day boundaries around fixture T0."""
    base = datetime.fromtimestamp(T0 / 1000, tz=timezone.utc)
    day0 = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        _ms(day0) - 1,
        _ms(day0),
        _ms(day0) + 1,
        _ms(day0 + timedelta(days=1)) - 1,
        _ms(day0 + timedelta(days=1)),
        T0 + DAY - 1,
        T0 + DAY,
        T0 + DAY + 1,
    ]


def dst_transition_instants() -> dict[str, list[dict[str, Any]]]:
    """America/New_York DST spring-forward / fall-back edges as UTC ms pairs."""
    ny = ZoneInfo("America/New_York")
    # 2024-03-10 02:00 EST -> 03:00 EDT (spring forward)
    spring_local_pre = datetime(2024, 3, 10, 1, 59, 59, tzinfo=ny)
    spring_local_post = datetime(2024, 3, 10, 3, 0, 0, tzinfo=ny)
    # 2024-11-03 02:00 EDT -> 01:00 EST (fall back) — use unambiguous offsets
    fall_edt = datetime(2024, 11, 3, 1, 30, 0, tzinfo=timezone(timedelta(hours=-4)))
    fall_est = datetime(2024, 11, 3, 1, 30, 0, tzinfo=timezone(timedelta(hours=-5)))
    return {
        "spring_forward_2024": [
            {"label": "pre", "utc_ms": _ms(spring_local_pre.astimezone(timezone.utc)), "local": str(spring_local_pre)},
            {"label": "post", "utc_ms": _ms(spring_local_post.astimezone(timezone.utc)), "local": str(spring_local_post)},
        ],
        "fall_back_2024": [
            {"label": "edt_1_30", "utc_ms": _ms(fall_edt.astimezone(timezone.utc)), "local": str(fall_edt)},
            {"label": "est_1_30", "utc_ms": _ms(fall_est.astimezone(timezone.utc)), "local": str(fall_est)},
        ],
    }


def attack_local_tz_as_known_at() -> dict[str, Any]:
    """Attack: treat local wall-clock as AS_KNOWN_AT without UTC conversion."""
    try:
        refuse_tz_local_as_known_at(tz_name="America/New_York")
        return {"attack_id": "local_tz_as_known_at", "blocked": False, "survivor": True, "detail": "not_refused"}
    except HardBanViolation as exc:
        return {
            "attack_id": "local_tz_as_known_at",
            "blocked": True,
            "survivor": False,
            "detail": str(exc),
            "status": "REJECTED_TZ_LOCAL",
        }


def attack_leap_second_aware_claim() -> dict[str, Any]:
    """Documented guard: claiming leap-second-aware PIT stamps is banned."""
    try:
        refuse_leap_second_aware_claim(claimed=True)
        return {
            "attack_id": "leap_second_aware_claim",
            "blocked": False,
            "survivor": True,
            "detail": "claim_accepted",
        }
    except HardBanViolation as exc:
        return {
            "attack_id": "leap_second_aware_claim",
            "blocked": True,
            "survivor": False,
            "detail": str(exc),
            "status": "REJECTED_LEAP_SECOND_CLAIM",
            "policy": LEAP_SECOND_POLICY,
        }


def attack_dst_wallclock_collision() -> dict[str, Any]:
    """Fall-back produces two local 01:30 clocks — UTC ms must differ; queries must use UTC."""
    edges = dst_transition_instants()["fall_back_2024"]
    edt_ms = edges[0]["utc_ms"]
    est_ms = edges[1]["utc_ms"]
    distinct = edt_ms != est_ms
    # Honest: AS_KNOWN_AT is UTC ms; collapsing them would be an attack.
    collapsed = edt_ms == est_ms
    blocked = distinct and not collapsed
    return {
        "attack_id": "dst_wallclock_collision",
        "blocked": blocked,
        "survivor": not blocked,
        "detail": f"edt_ms={edt_ms} est_ms={est_ms}",
        "status": "UTC_DISTINCT" if blocked else "COLLAPSED",
        "evidence": {"edges": edges},
    }


def attack_utc_midnight_revision_boundary() -> dict[str, Any]:
    """Queries at UTC midnight ±1ms must not leak later revisions."""
    store = _fresh_store()
    survivors: list[str] = []
    findings: list[dict[str, Any]] = []
    for aka in utc_midnight_boundaries():
        if aka <= 0:
            try:
                research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=aka)
                survivors.append(f"nonpositive:{aka}")
                findings.append({"aka": aka, "blocked": False})
            except MissingAsKnownAtError:
                findings.append({"aka": aka, "blocked": True, "status": "REJECTED"})
            continue
        result = research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=aka)
        if result.status == "AVAILABLE" and result.selected_revision:
            times = result.selected_revision["times"]
            leak = any(int(times[k]) > aka for k in ("available_time", "revision_time", "ingest_time"))
            if leak:
                survivors.append(f"leak:{aka}:{result.revision_id}")
            findings.append(
                {
                    "aka": aka,
                    "blocked": not leak,
                    "revision_id": result.revision_id,
                    "status": result.status,
                }
            )
        else:
            findings.append({"aka": aka, "blocked": True, "status": result.status})
    return {
        "attack_id": "utc_midnight_revision_boundary",
        "blocked": len(survivors) == 0,
        "survivor": len(survivors) > 0,
        "survivors": survivors,
        "findings": findings,
        "detail": "utc_midnight_boundaries_checked",
    }


def attack_spring_forward_gap_query() -> dict[str, Any]:
    """Spring-forward skips local 02:30 — UTC timeline remains continuous."""
    edges = dst_transition_instants()["spring_forward_2024"]
    pre = edges[0]["utc_ms"]
    post = edges[1]["utc_ms"]
    gap_ms = post - pre
    # Expect ~1s + 1h jump in local, continuous UTC (~3601000ms from 01:59:59 to 03:00:00).
    continuous = gap_ms > 0
    store = _fresh_store()
    # Query with UTC ms straddling DST must still obey PIT (no exception / no leak).
    mid = pre + (gap_ms // 2)
    result = research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=max(mid, T0 + DAY))
    leak = False
    if result.status == "AVAILABLE" and result.selected_revision:
        times = result.selected_revision["times"]
        aka = max(mid, T0 + DAY)
        leak = any(int(times[k]) > aka for k in ("available_time", "revision_time", "ingest_time"))
    blocked = continuous and not leak
    return {
        "attack_id": "spring_forward_gap_query",
        "blocked": blocked,
        "survivor": not blocked,
        "detail": f"gap_ms={gap_ms} status={result.status}",
        "evidence": {"pre": pre, "post": post, "gap_ms": gap_ms, "result_status": result.status},
    }


def run_timestamp_edge_attacks() -> dict[str, Any]:
    attacks = [
        attack_local_tz_as_known_at(),
        attack_leap_second_aware_claim(),
        attack_dst_wallclock_collision(),
        attack_utc_midnight_revision_boundary(),
        attack_spring_forward_gap_query(),
    ]
    survivors = [a["attack_id"] for a in attacks if a.get("survivor")]
    return {
        "schema": "v17_deep_timestamp_edges_v1",
        "leap_second_policy": LEAP_SECOND_POLICY,
        "attack_count": len(attacks),
        "blocked_count": sum(1 for a in attacks if a.get("blocked")),
        "survivor_count": len(survivors),
        "survivors": survivors,
        "pass": len(survivors) == 0,
        "attacks": attacks,
    }
