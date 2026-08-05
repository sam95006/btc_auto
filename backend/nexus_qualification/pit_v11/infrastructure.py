"""Founder V11 point-in-time qualification infrastructure.

Blocked-only implementation for synthetic fixtures. It wires dataset lineage,
point-in-time availability checks, semantic checksums, interval registries,
OOS seals, Founder authorization, and promotion blocking without selecting a
strategy or executing Walk-forward, OOS, Demo, or promotion.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_ID = "FOUNDER_V11_POINT_IN_TIME_QUALIFICATION"
PIT_STATUS_BLOCKED_READY = "BLOCKED_READY"
STAGE_STATUS_BLOCKED_READY = "BLOCKED_READY"
ARTIFACT_REL = Path("artifacts/readiness/immutable/v11_point_in_time_qualification")

QUALIFICATION_STAGES: tuple[str, ...] = (
    "DATASET_LINEAGE_REGISTERED",
    "POINT_IN_TIME_TIMESTAMPS_VERIFIED",
    "FUTURE_DATA_EXCLUSION_PROVEN",
    "CANDIDATE_SEMANTIC_CHECKSUMS_STAMPED",
    "INTERVAL_REGISTRIES_REGISTERED",
    "OOS_CRYPTOGRAPHIC_SEAL_CREATED",
    "OOS_NON_CONSUMPTION_PROVEN",
    "FOUNDER_AUTHORIZATION_GATE_EVALUATED",
    "PROMOTION_STATE_MACHINE_BLOCKED",
)

OOS_FALSE_FLAGS: tuple[str, ...] = (
    "oos_reservation_created",
    "oos_downloaded",
    "oos_executed",
    "oos_consumed",
    "oos_metrics_computed",
    "oos_revealed_to_candidate",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def synthetic_candidate_fixture() -> dict[str, Any]:
    return {
        "candidate_id": "SYNTHETIC_V11_PIT_CANDIDATE",
        "candidate_label": "synthetic_fixture_not_selected",
        "model_family": "other_models_synthetic_fixture",
        "strategy_family": "SYNTHETIC_POINT_IN_TIME_FAMILY",
        "economic_mechanism": "synthetic_non_trading_placeholder",
        "parameters": {"lookback": 12, "threshold": 0.0, "fixture_marker": True},
        "parameter_source": "synthetic_fixture",
        "code_ref": "backend/nexus_qualification/pit_v11",
        "dataset_ref": "SYNTHETIC_PIT_DATASET_V11",
        "preregistration_timestamp": "2026-01-01T00:00:00Z",
        "fixture_only": True,
        "selected": False,
        "promoted": False,
    }


def synthetic_dataset_lineage(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    source_ts = as_of_ms - 14 * 86_400_000
    retrieval_ts = as_of_ms - 7 * 86_400_000
    availability_ts = as_of_ms - 6 * 86_400_000
    records = [
        {
            "record_id": "SYN_PIT_BAR_001",
            "symbol": "SYNTHUSDT",
            "source_timestamp_ms": source_ts,
            "retrieval_timestamp_ms": retrieval_ts,
            "availability_timestamp_ms": availability_ts,
            "available_as_of_ms": availability_ts,
            "value_kind": "synthetic_ohlcv_bar",
            "fixture_only": True,
        }
    ]
    lineage = {
        "dataset_id": "SYNTHETIC_PIT_DATASET_V11",
        "dataset_version": "v11.synthetic.1",
        "source": "synthetic_fixture_generator",
        "source_timestamp_ms": source_ts,
        "retrieval_timestamp_ms": retrieval_ts,
        "availability_timestamp_ms": availability_ts,
        "as_of_ms": as_of_ms,
        "records": records,
        "real_market_data": False,
        "fixture_only": True,
    }
    lineage["dataset_checksum"] = sha_obj(records)
    lineage["dataset_semantic_checksum"] = sha_obj(
        {
            "dataset_id": lineage["dataset_id"],
            "dataset_version": lineage["dataset_version"],
            "source": lineage["source"],
            "record_shapes": [
                {
                    "symbol": r["symbol"],
                    "value_kind": r["value_kind"],
                    "available_as_of_ms": r["available_as_of_ms"],
                }
                for r in records
            ],
        }
    )
    return lineage


@dataclass(frozen=True)
class IntervalRecord:
    interval_id: str
    label: str
    start_ms: int
    end_ms: int
    category: str

    def overlaps(self, other: "IntervalRecord") -> bool:
        return not (self.end_ms < other.start_ms or other.end_ms < self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntervalRegistry:
    kind: str
    intervals: list[IntervalRecord] = field(default_factory=list)

    def add(self, record: IntervalRecord) -> None:
        if record.end_ms < record.start_ms:
            raise ValueError(f"interval_inverted:{record.interval_id}")
        self.intervals.append(record)

    def checksum(self) -> str:
        body = [r.to_dict() for r in sorted(self.intervals, key=lambda x: (x.start_ms, x.end_ms, x.interval_id))]
        return sha_obj({"kind": self.kind, "intervals": body})

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "interval_count": len(self.intervals),
            "checksum": self.checksum(),
            "intervals": [r.to_dict() for r in self.intervals],
        }


def synthetic_interval_registries(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, IntervalRegistry]:
    consumed = IntervalRegistry("consumed")
    reserved = IntervalRegistry("reserved")
    availability = IntervalRegistry("availability")
    consumed.add(
        IntervalRecord(
            "SYN_V11_CONSUMED_DEV",
            "synthetic_consumed_development",
            as_of_ms - 60 * 86_400_000,
            as_of_ms - 30 * 86_400_000,
            "consumed",
        )
    )
    reserved.add(
        IntervalRecord(
            "SYN_V11_RESERVED_OOS",
            "synthetic_reserved_untouched_oos",
            as_of_ms - 20 * 86_400_000,
            as_of_ms - 10 * 86_400_000,
            "reserved",
        )
    )
    availability.add(
        IntervalRecord(
            "SYN_V11_AVAILABLE_PIT",
            "synthetic_available_before_as_of",
            as_of_ms - 14 * 86_400_000,
            as_of_ms - 6 * 86_400_000,
            "availability",
        )
    )
    return {"consumed": consumed, "reserved": reserved, "availability": availability}


def semantic_checksums(candidate: dict[str, Any], dataset: dict[str, Any], code_checksum: str) -> dict[str, str]:
    return {
        "candidate_checksum": sha_obj(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_label": candidate["candidate_label"],
                "fixture_only": candidate["fixture_only"],
                "preregistration_timestamp": candidate["preregistration_timestamp"],
            }
        ),
        "candidate_semantic_checksum": sha_obj(
            {
                "model_family": candidate["model_family"],
                "strategy_family": candidate["strategy_family"],
                "economic_mechanism": candidate["economic_mechanism"],
                "dataset_ref": candidate["dataset_ref"],
                "code_ref": candidate["code_ref"],
            }
        ),
        "parameter_checksum": sha_obj(candidate["parameters"]),
        "code_checksum": code_checksum,
        "dataset_checksum": dataset["dataset_checksum"],
        "dataset_semantic_checksum": dataset["dataset_semantic_checksum"],
    }


def compute_code_checksum(root: Path | None = None) -> str:
    base = Path(root) if root is not None else Path(__file__).resolve().parent
    payload: list[dict[str, str]] = []
    for path in sorted(base.glob("*.py")):
        payload.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return sha_obj(payload)


_TIMESTAMP_EXACT_KEYS = frozenset(
    {
        "available_as_of_ms",
        "as_of_ms",
        "availability_timestamp_ms",
        "source_timestamp_ms",
        "retrieval_timestamp_ms",
        "bar_close_ts_ms",
        "nested_available_as_of_ms",
    }
)


def _is_timestamp_key(key: str) -> bool:
    k = str(key)
    if k in _TIMESTAMP_EXACT_KEYS:
        return True
    return k.endswith("_timestamp_ms") or k.endswith("_ts_ms") or k.endswith("_as_of_ms")


def _walk_future_timestamps(node: Any, *, as_of_ms: int, path: str = "") -> list[dict[str, Any]]:
    """Recursively collect timestamp fields whose value exceeds as_of_ms."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            if _is_timestamp_key(str(key)):
                try:
                    ts = int(value)
                except (TypeError, ValueError):
                    ts = None
                if ts is not None and ts > as_of_ms:
                    found.append({"path": child_path, "key": str(key), "value_ms": ts, "as_of_ms": as_of_ms})
            found.extend(_walk_future_timestamps(value, as_of_ms=as_of_ms, path=child_path))
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            found.extend(_walk_future_timestamps(item, as_of_ms=as_of_ms, path=f"{path}[{idx}]"))
    return found


def prove_future_data_exclusion(dataset: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    """Fail closed on any top-level or nested evidence timestamp after as_of."""
    violations: list[dict[str, Any]] = []
    for r in dataset.get("records") or []:
        for hit in _walk_future_timestamps(r, as_of_ms=as_of_ms, path=str(r.get("record_id") or "record")):
            violations.append({"record_id": r.get("record_id"), "kind": "nested_or_top", **hit})
    for hit in _walk_future_timestamps(
        {k: v for k, v in dataset.items() if k != "records"},
        as_of_ms=as_of_ms,
        path="dataset",
    ):
        # Dataset as_of_ms is the cutoff itself, never a violation.
        if hit.get("key") == "as_of_ms" and int(hit.get("value_ms") or 0) == as_of_ms:
            continue
        violations.append({"record_id": None, "kind": "dataset", **hit})
    return {
        "status": "FUTURE_DATA_EXCLUDED" if not violations else "FUTURE_DATA_VIOLATION",
        "allowed": not violations,
        "future_data_excluded": not violations,
        "as_of_ms": as_of_ms,
        "violation_count": len(violations),
        "violations": violations,
        "nested_scan": True,
    }


def prove_oos_non_consumption(registries: dict[str, IntervalRegistry]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    consumed = registries["consumed"].intervals
    reserved = registries["reserved"].intervals
    for reserved_iv in reserved:
        for consumed_iv in consumed:
            if reserved_iv.overlaps(consumed_iv):
                violations.append({"reserved": reserved_iv.to_dict(), "consumed": consumed_iv.to_dict()})
    return {
        "status": "OOS_NON_CONSUMPTION_PROVEN" if not violations else "OOS_NON_CONSUMPTION_FAILED",
        "proven": not violations,
        "oos_consumed": False,
        "oos_executed": False,
        "formal_walk_forward_executed": False,
        "violations": violations,
        "registry_checksums": {k: v.checksum() for k, v in registries.items()},
    }


@dataclass
class OOSSealLineage:
    """Write-once OOS seal authority with anti-regeneration fail-closed checks."""

    seals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def reset(self) -> None:
        self.seals.clear()


_DEFAULT_OOS_SEAL_LINEAGE = OOSSealLineage()


def reset_oos_seal_lineage(lineage: OOSSealLineage | None = None) -> None:
    (lineage or _DEFAULT_OOS_SEAL_LINEAGE).reset()


def build_oos_cryptographic_seal(
    registries: dict[str, IntervalRegistry],
    checksums: dict[str, str],
    *,
    lineage_key: str = "default",
    lineage: OOSSealLineage | None = None,
) -> dict[str, Any]:
    """Create a write-once OOS seal; regenerating after reserved mutation fails closed."""
    store = lineage if lineage is not None else _DEFAULT_OOS_SEAL_LINEAGE
    seal_payload = {
        "reserved_registry_checksum": registries["reserved"].checksum(),
        "candidate_checksum": checksums["candidate_checksum"],
        "dataset_semantic_checksum": checksums["dataset_semantic_checksum"],
        "status": "SEALED_NOT_CONSUMED",
        "fixture_only": True,
    }
    computed_seal = sha_obj(seal_payload)
    prior = store.seals.get(lineage_key)
    if prior is not None:
        reserved_mutated = prior["reserved_registry_checksum"] != seal_payload["reserved_registry_checksum"]
        checksum_mutated = (
            prior["candidate_checksum"] != seal_payload["candidate_checksum"]
            or prior["dataset_semantic_checksum"] != seal_payload["dataset_semantic_checksum"]
        )
        if reserved_mutated or checksum_mutated or prior["seal"] != computed_seal:
            return {
                "reserved_registry_checksum": seal_payload["reserved_registry_checksum"],
                "candidate_checksum": seal_payload["candidate_checksum"],
                "dataset_semantic_checksum": seal_payload["dataset_semantic_checksum"],
                "status": "SEAL_REGENERATION_REJECTED_RESERVED_MUTATION"
                if reserved_mutated
                else "SEAL_REGENERATION_REJECTED",
                "fixture_only": True,
                "seal_algorithm": "sha256_json_canonical",
                "seal": None,
                "prior_seal": prior["seal"],
                "computed_seal_rejected": computed_seal,
                "allowed": False,
                "fail_closed": True,
                "write_once": True,
                "lineage_key": lineage_key,
                "oos_revealed_to_candidate": False,
                "oos_consumed": False,
            }
        # Identical recompute is allowed and returns the persisted seal.
        return {
            **seal_payload,
            "seal_algorithm": "sha256_json_canonical",
            "seal": prior["seal"],
            "allowed": True,
            "fail_closed": False,
            "write_once": True,
            "lineage_key": lineage_key,
            "lineage_verified": True,
            "oos_revealed_to_candidate": False,
            "oos_consumed": False,
        }

    result = {
        **seal_payload,
        "seal_algorithm": "sha256_json_canonical",
        "seal": computed_seal,
        "allowed": True,
        "fail_closed": False,
        "write_once": True,
        "lineage_key": lineage_key,
        "lineage_verified": True,
        "oos_revealed_to_candidate": False,
        "oos_consumed": False,
    }
    store.seals[lineage_key] = {
        "seal": computed_seal,
        "reserved_registry_checksum": seal_payload["reserved_registry_checksum"],
        "candidate_checksum": seal_payload["candidate_checksum"],
        "dataset_semantic_checksum": seal_payload["dataset_semantic_checksum"],
        "status": "SEALED_NOT_CONSUMED",
    }
    return result


@dataclass
class FounderAuthorizationGate:
    authorized: bool = False
    reason: str = "FOUNDER_AUTHORIZATION_MISSING"
    required_scope: str = "founder_v11_pit_qualification"
    _binding_secret: str = field(default="v11_pit_founder_gate_binding_v1", repr=False)

    def _binding_payload(self, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "authorized": bool(body.get("authorized")),
            "reason": str(body.get("reason") or ""),
            "required_scope": str(body.get("required_scope") or self.required_scope),
            "binding_domain": self._binding_secret,
        }

    def bind_result(self, body: dict[str, Any]) -> str:
        return sha_obj(self._binding_payload(body))

    def verify_bound_result(self, body: dict[str, Any] | None) -> dict[str, Any]:
        """Integrity-check a founder-auth dict; spoofed authorized=True fails closed."""
        if not isinstance(body, dict):
            return {
                "valid": False,
                "authorized": False,
                "reason": "FOUNDER_AUTH_PROOF_MISSING",
                "spoof_rejected": False,
            }
        claimed = dict(body)
        proof = claimed.get("auth_proof") or claimed.get("auth_binding")
        expected = self.bind_result(claimed)
        if proof != expected:
            return {
                "valid": False,
                "authorized": False,
                "reason": "FOUNDER_AUTH_PROOF_INVALID_OR_SPOOFED",
                "spoof_rejected": bool(claimed.get("authorized") is True),
                "expected_auth_proof": expected,
                "provided_auth_proof": proof,
            }
        # Even a valid binding never grants promotion in V11 blocked-only infra.
        return {
            "valid": True,
            "authorized": False,
            "reason": claimed.get("reason") or self.reason,
            "spoof_rejected": False,
            "bound_authorized_claim": bool(claimed.get("authorized")),
        }

    def evaluate(self, request: dict[str, Any] | None) -> dict[str, Any]:
        req = dict(request or {})
        if not req.get("founder_authorization_token"):
            self.authorized = False
            self.reason = "FOUNDER_AUTHORIZATION_MISSING"
        else:
            self.authorized = False
            self.reason = "FOUNDER_AUTHORIZATION_DENIED_BLOCKED_ONLY_V11"
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        body = {
            "authorized": self.authorized,
            "reason": self.reason,
            "required_scope": self.required_scope,
        }
        body["auth_proof"] = self.bind_result(body)
        body["auth_binding"] = body["auth_proof"]
        return body


@dataclass
class PromotionStateMachine:
    state: str = "BLOCKED_READY"
    stages: dict[str, str] = field(default_factory=lambda: {s: STAGE_STATUS_BLOCKED_READY for s in QUALIFICATION_STAGES})
    history: list[dict[str, Any]] = field(default_factory=list)
    founder_gate: FounderAuthorizationGate = field(default_factory=FounderAuthorizationGate)

    def attempt_promote(self, founder_auth_result: dict[str, Any] | None = None) -> dict[str, Any]:
        """Always BLOCKED_READY; requires integrity-bound Founder gate proof consultation."""
        if founder_auth_result is None:
            founder_auth_result = self.founder_gate.evaluate(None)
        proof = self.founder_gate.verify_bound_result(founder_auth_result)
        result = {
            "allowed": False,
            "reason": "PROMOTION_BLOCKED_READY_V11_INFRASTRUCTURE_ONLY",
            "state": "PROMOTION_BLOCKED_READY",
            "selected_strategy": None,
            "formal_walk_forward_executed": False,
            "oos_executed": False,
            "demo_order_count": 0,
            "founder_authorization_gate": deepcopy(founder_auth_result),
            "founder_auth_verified": bool(proof.get("valid")),
            "founder_auth_proof": proof,
            "founder_authorized": False,
        }
        # Spoofed authorized=True must never open a promotion path.
        if founder_auth_result.get("authorized") is True and not proof.get("valid"):
            result["reason"] = "FOUNDER_AUTH_SPOOF_REJECTED_PROMOTION_BLOCKED"
            result["allowed"] = False
        self.state = "PROMOTION_BLOCKED_READY"
        self.history.append({"event": "attempt_promote", "result": deepcopy(result)})
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "stages": dict(self.stages),
            "stage_order": list(QUALIFICATION_STAGES),
            "history": deepcopy(self.history),
            "founder_gate": self.founder_gate.to_dict(),
        }


class PointInTimeQualificationV11:
    def __init__(self) -> None:
        self.status = PIT_STATUS_BLOCKED_READY
        self.created_at = _utc()
        self.founder_gate = FounderAuthorizationGate()
        self.promotion_sm = PromotionStateMachine(founder_gate=self.founder_gate)
        self.oos_seal_lineage = OOSSealLineage()
        self.proofs: dict[str, Any] = {}
        self.summary_payload: dict[str, Any] | None = None

    def bootstrap_synthetic(self, *, as_of_ms: int = 1_700_000_000_000, code_root: Path | None = None) -> dict[str, Any]:
        candidate = synthetic_candidate_fixture()
        dataset = synthetic_dataset_lineage(as_of_ms=as_of_ms)
        registries = synthetic_interval_registries(as_of_ms=as_of_ms)
        checksums = semantic_checksums(candidate, dataset, compute_code_checksum(code_root))
        candidate = {**candidate, **checksums}

        future_proof = prove_future_data_exclusion(dataset, as_of_ms=as_of_ms)
        oos_proof = prove_oos_non_consumption(registries)
        oos_seal = build_oos_cryptographic_seal(
            registries,
            checksums,
            lineage_key=f"bootstrap:{as_of_ms}",
            lineage=self.oos_seal_lineage,
        )
        founder = self.founder_gate.evaluate(None)
        promotion_attempt = self.promotion_sm.attempt_promote(founder)

        self.proofs = {
            "future_data_exclusion": future_proof,
            "oos_non_consumption": oos_proof,
            "oos_cryptographic_seal": oos_seal,
            "founder_authorization_gate": founder,
            "promotion_attempt": promotion_attempt,
        }
        self.summary_payload = {
            "schema": SCHEMA_ID,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "as_of_ms": as_of_ms,
            "candidate": candidate,
            "dataset_lineage": dataset,
            "checksums": checksums,
            "registries": {k: v.to_dict() for k, v in registries.items()},
            "oos_cryptographic_seal": oos_seal,
            "oos_non_consumption_proof": oos_proof,
            "founder_authorization_gate": founder,
            "promotion_state_machine": self.promotion_sm.to_dict(),
            "stage_order": list(QUALIFICATION_STAGES),
            "stages": dict(self.promotion_sm.stages),
            "all_stages_blocked_ready": all(v == STAGE_STATUS_BLOCKED_READY for v in self.promotion_sm.stages.values()),
            "formal_walk_forward_executed": False,
            "demo_order_count": 0,
            "exchange_write_attempt_count": 0,
            "selected_strategy": None,
            "strategy_selected": False,
            "strategy_promoted": False,
            "demo_eligibility": False,
            **{flag: False for flag in OOS_FALSE_FLAGS},
            "hard_bans": {
                "select_strategy": "NOT_PERFORMED",
                "real_walk_forward": "NOT_EXECUTED",
                "real_oos": "NOT_CONSUMED",
                "demo": "NOT_RUN",
                "promotion": "BLOCKED",
                "fixtures": "SYNTHETIC_ONLY",
            },
            "proofs": deepcopy(self.proofs),
        }
        return deepcopy(self.summary_payload)


def run_point_in_time_qualification_dry_run(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    return PointInTimeQualificationV11().bootstrap_synthetic(as_of_ms=as_of_ms)


def write_immutable_artifacts(summary: dict[str, Any], *, root: Path | None = None) -> dict[str, Path]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    docs = {
        "status": {
            "schema": SCHEMA_ID,
            "status": summary["status"],
            "all_stages_blocked_ready": summary["all_stages_blocked_ready"],
            "formal_walk_forward_executed": False,
            **{flag: False for flag in OOS_FALSE_FLAGS},
            "demo_order_count": 0,
            "selected_strategy": None,
            "strategy_promoted": False,
        },
        "dataset_lineage": summary["dataset_lineage"],
        "semantic_checksums": summary["checksums"],
        "interval_registries": summary["registries"],
        "oos_cryptographic_seal": summary["oos_cryptographic_seal"],
        "oos_non_consumption_proof": summary["oos_non_consumption_proof"],
        "founder_authorization_gate": summary["founder_authorization_gate"],
        "promotion_state_machine": summary["promotion_state_machine"],
        "stage_matrix": {"stage_order": summary["stage_order"], "stages": summary["stages"]},
        "summary": summary,
    }

    paths: dict[str, Path] = {}
    for name, doc in docs.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths[name] = path
    return paths


def main() -> int:
    summary = run_point_in_time_qualification_dry_run()
    paths = write_immutable_artifacts(summary)
    print(json.dumps({"status": summary["status"], "artifacts": {k: str(v) for k, v in paths.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
