"""Property-based + mutation-style attacks on AS_KNOWN_AT / revision selection."""
from __future__ import annotations

import random
from typing import Any

from backend.nexus_deep_pit_survivorship.constants import (
    MUTATION_CASE_COUNT,
    PROPERTY_CASE_COUNT,
    PROPERTY_SEED,
)
from backend.nexus_pit_revision_v17.fixtures import DAY, T0, build_revision_catalog
from backend.nexus_pit_revision_v17.hard_bans import (
    FutureLeakageError,
    MissingAsKnownAtError,
    TodayRevisionForPastBacktestError,
)
from backend.nexus_pit_revision_v17.store import (
    PitRevisionStore,
    assert_no_future_axes,
    is_visible_as_known_at,
    prove_pit_visibility,
    research_query,
)
from backend.nexus_pit_revision_v17.types import DualTimeStamp, ResearchQuery, RevisionRecord


def _fresh_store() -> PitRevisionStore:
    store = PitRevisionStore()
    store.ingest_many(build_revision_catalog())
    return store


def _property_no_future_axes(store: PitRevisionStore, *, as_known_at: int, series_id: str) -> dict[str, Any]:
    proof = prove_pit_visibility(store, series_id=series_id, as_known_at=as_known_at)
    visible = store.visible_revisions(series_id, as_known_at=as_known_at)
    for rev in visible:
        try:
            assert_no_future_axes(rev, as_known_at=as_known_at)
        except FutureLeakageError as exc:
            return {
                "ok": False,
                "survivor": True,
                "detail": f"future_axis_in_visible:{exc}",
                "proof": proof,
            }
        if not is_visible_as_known_at(rev, as_known_at=as_known_at):
            return {
                "ok": False,
                "survivor": True,
                "detail": "visibility_predicate_mismatch",
                "proof": proof,
            }
    selected = store.select_as_known_at(series_id, as_known_at=as_known_at)
    if selected is not None:
        if (
            selected.available_time > as_known_at
            or selected.revision_time > as_known_at
            or selected.ingest_time > as_known_at
        ):
            return {
                "ok": False,
                "survivor": True,
                "detail": f"selected_future:{selected.revision_id}",
                "proof": proof,
            }
    return {
        "ok": proof["pit_holds"] and len(proof["leaked_revision_ids"]) == 0,
        "survivor": False,
        "detail": "property_holds",
        "proof": proof,
        "visible_count": len(visible),
        "selected": None if selected is None else selected.revision_id,
    }


def run_property_as_known_at_campaign(*, seed: int = PROPERTY_SEED, n: int = PROPERTY_CASE_COUNT) -> dict[str, Any]:
    """For random AS_KNOWN_AT values, no revision axis may exceed the query time."""
    rng = random.Random(seed)
    store = _fresh_store()
    series_ids = sorted({r.series_id for r in build_revision_catalog()})
    cases: list[dict[str, Any]] = []
    survivors: list[str] = []

    # Include exact revision boundaries (±0/±1) for every catalog revision.
    boundary_akas: list[int] = []
    for rev in build_revision_catalog():
        for axis in (rev.available_time, rev.revision_time, rev.ingest_time):
            boundary_akas.extend([axis - 1, axis, axis + 1])

    for aka in boundary_akas:
        for series_id in series_ids:
            result = _property_no_future_axes(store, as_known_at=aka, series_id=series_id)
            case_id = f"boundary:{series_id}:{aka}"
            cases.append({"case_id": case_id, **result})
            if result.get("survivor") or not result.get("ok"):
                survivors.append(case_id)

    for i in range(n):
        aka = T0 + rng.randint(0, 40) * DAY + rng.randint(-3, 3)
        series_id = series_ids[rng.randrange(len(series_ids))]
        result = _property_no_future_axes(store, as_known_at=aka, series_id=series_id)
        case_id = f"rand:{i}:{series_id}:{aka}"
        cases.append({"case_id": case_id, **result})
        if result.get("survivor") or not result.get("ok"):
            survivors.append(case_id)

    return {
        "schema": "v17_deep_property_as_known_at_v1",
        "seed": seed,
        "case_count": len(cases),
        "survivor_count": len(survivors),
        "survivors": survivors,
        "pass": len(survivors) == 0,
        "cases_sample": cases[:8],
    }


def _mutate_query(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Apply a single mutation to a research query payload."""
    q = dict(base)
    op = rng.choice(
        [
            "drop_aka",
            "null_aka",
            "zero_aka",
            "negative_aka",
            "float_aka",
            "string_aka",
            "allow_latest",
            "aka_minus_one",
            "aka_plus_one",
            "wrong_series",
            "future_event_filter",
        ]
    )
    q["_mutation"] = op
    if op == "drop_aka":
        q.pop("as_known_at", None)
    elif op == "null_aka":
        q["as_known_at"] = None
    elif op == "zero_aka":
        q["as_known_at"] = 0
    elif op == "negative_aka":
        q["as_known_at"] = -1
    elif op == "float_aka":
        q["as_known_at"] = float(q.get("as_known_at") or T0) + 0.5
    elif op == "string_aka":
        q["as_known_at"] = str(q.get("as_known_at") or T0)
    elif op == "allow_latest":
        q["allow_latest_revision"] = True
        q["as_known_at"] = T0 + 3 * DAY
    elif op == "aka_minus_one":
        q["as_known_at"] = int(q["as_known_at"]) - 1
    elif op == "aka_plus_one":
        q["as_known_at"] = int(q["as_known_at"]) + 1
    elif op == "wrong_series":
        q["series_id"] = "SYNTH.DOES.NOT.EXIST"
    elif op == "future_event_filter":
        q["event_time"] = T0 + 2 * DAY
        q["series_id"] = "SYNTH.ETHUSDT.CLOSE"
        q["as_known_at"] = T0 + 3 * DAY
    return q


def _mutation_blocked(store: PitRevisionStore, mutated: dict[str, Any]) -> dict[str, Any]:
    op = mutated.get("_mutation")
    payload = {k: v for k, v in mutated.items() if not k.startswith("_")}

    # Mutations that must be refused / unavailable (not leak future tip).
    try:
        if "as_known_at" not in payload or payload.get("as_known_at") is None:
            research_query(store, payload)  # type: ignore[arg-type]
            return {"blocked": False, "detail": "accepted_missing_aka", "op": op}
        aka = payload["as_known_at"]
        # Non-int aka: int() may coerce float/string — still must not leak.
        if isinstance(aka, bool) or aka is None:
            research_query(store, payload)  # type: ignore[arg-type]
            return {"blocked": False, "detail": "accepted_bad_aka", "op": op}
        if isinstance(aka, (int, float, str)):
            try:
                aka_i = int(float(aka)) if not isinstance(aka, int) else aka
            except (TypeError, ValueError):
                return {"blocked": True, "detail": "aka_parse_failed", "op": op, "status": "PARSE_FAIL"}
            if aka_i <= 0:
                try:
                    research_query(store, payload)  # type: ignore[arg-type]
                    return {"blocked": False, "detail": "accepted_nonpositive_aka", "op": op}
                except MissingAsKnownAtError:
                    return {"blocked": True, "detail": "rejected_nonpositive", "op": op, "status": "REJECTED"}

        if op == "allow_latest":
            try:
                research_query(
                    store,
                    ResearchQuery(
                        series_id=str(payload["series_id"]),
                        as_known_at=int(payload["as_known_at"]),
                        allow_latest_revision=True,
                    ),
                )
                return {"blocked": False, "detail": "allowed_today_for_past", "op": op}
            except TodayRevisionForPastBacktestError:
                return {"blocked": True, "detail": "today_banned", "op": op, "status": "REJECTED"}

        result = research_query(store, payload)  # type: ignore[arg-type]
        # Must never return tip revision when aka is before tip.
        tip = store.latest_revision(str(payload["series_id"]))
        if tip is not None and result.status == "AVAILABLE" and result.revision_id == tip.revision_id:
            if tip.revision_time > int(float(payload["as_known_at"])):
                return {
                    "blocked": False,
                    "detail": f"leaked_tip:{result.revision_id}",
                    "op": op,
                    "status": result.status,
                }
        if op == "future_event_filter":
            ok = result.status == "UNAVAILABLE_AT_TIME"
            return {
                "blocked": ok,
                "detail": f"status={result.status}",
                "op": op,
                "status": result.status,
            }
        if op == "wrong_series":
            ok = result.status == "UNAVAILABLE_AT_TIME"
            return {"blocked": ok, "detail": f"status={result.status}", "op": op, "status": result.status}
        # Boundary ±1 mutations: selected revision axes must still be <= aka.
        if result.status == "AVAILABLE" and result.selected_revision:
            times = result.selected_revision["times"]
            aka_i = int(float(payload["as_known_at"]))
            leak = any(int(times[k]) > aka_i for k in ("available_time", "revision_time", "ingest_time"))
            return {
                "blocked": not leak,
                "detail": f"revision={result.revision_id}",
                "op": op,
                "status": result.status,
            }
        return {"blocked": True, "detail": f"status={result.status}", "op": op, "status": result.status}
    except MissingAsKnownAtError:
        return {"blocked": True, "detail": "missing_aka_rejected", "op": op, "status": "REJECTED"}
    except TodayRevisionForPastBacktestError:
        return {"blocked": True, "detail": "today_banned", "op": op, "status": "REJECTED"}
    except (TypeError, ValueError) as exc:
        # Coercion / type failures are fail-closed (blocked), not survivors.
        return {"blocked": True, "detail": f"type_fail:{type(exc).__name__}", "op": op, "status": "TYPE_FAIL"}
    except Exception as exc:  # noqa: BLE001
        return {
            "blocked": False,
            "survivor": True,
            "detail": f"UNEXPECTED:{type(exc).__name__}:{exc}",
            "op": op,
            "status": "ERROR",
        }


def run_mutation_as_known_at_campaign(
    *, seed: int = PROPERTY_SEED + 7, n: int = MUTATION_CASE_COUNT
) -> dict[str, Any]:
    rng = random.Random(seed)
    store = _fresh_store()
    base = {
        "series_id": "SYNTH.BTCUSDT.CLOSE",
        "as_known_at": T0 + 6 * DAY,
    }
    findings: list[dict[str, Any]] = []
    survivors: list[str] = []
    for i in range(n):
        mutated = _mutate_query(base, rng)
        result = _mutation_blocked(store, mutated)
        blocked = bool(result.get("blocked"))
        survivor = (not blocked) or bool(result.get("survivor"))
        finding = {
            "attack_id": f"mutation_{i}_{mutated.get('_mutation')}",
            "blocked": blocked,
            "survivor": survivor,
            "detail": result.get("detail"),
            "status": result.get("status"),
            "mutation": mutated.get("_mutation"),
        }
        findings.append(finding)
        if survivor:
            survivors.append(finding["attack_id"])

    return {
        "schema": "v17_deep_mutation_as_known_at_v1",
        "seed": seed,
        "attack_count": len(findings),
        "blocked_count": sum(1 for f in findings if f["blocked"]),
        "survivor_count": len(survivors),
        "survivors": survivors,
        "pass": len(survivors) == 0,
        "findings_sample": findings[:10],
    }


def inject_mutated_revision_axes(*, as_known_at: int) -> dict[str, Any]:
    """Mutation: push one dual-time axis past AS_KNOWN_AT — must raise FutureLeakageError."""
    axes = ("available_time", "revision_time", "ingest_time")
    blocked = 0
    survivors: list[str] = []
    for axis in axes:
        times = {
            "event_time": T0,
            "available_time": T0 + DAY,
            "revision_time": T0 + DAY,
            "ingest_time": T0 + DAY,
        }
        times[axis] = as_known_at + DAY
        # Keep ordering valid where possible; if invalid DualTimeStamp, still count as blocked.
        try:
            if axis == "available_time":
                times["revision_time"] = times["available_time"]
                times["ingest_time"] = times["available_time"]
            elif axis == "revision_time":
                times["ingest_time"] = times["revision_time"]
            record = RevisionRecord(
                revision_id=f"MUT_{axis}",
                series_id="SYNTH.BTCUSDT.CLOSE",
                kind="OBSERVATION",
                value=1.0,
                times=DualTimeStamp(**times),
            )
            try:
                assert_no_future_axes(record, as_known_at=as_known_at)
                survivors.append(axis)
            except FutureLeakageError:
                blocked += 1
        except ValueError:
            blocked += 1  # invalid stamp rejected — fail closed
    return {
        "attack_id": "mutate_revision_axes_past_aka",
        "blocked": len(survivors) == 0,
        "survivor": len(survivors) > 0,
        "blocked_count": blocked,
        "survivors": survivors,
        "detail": "axis_mutations_checked",
    }
