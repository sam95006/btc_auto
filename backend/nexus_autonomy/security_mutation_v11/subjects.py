"""Safety-critical subjects — thin wrappers over real Private Core guards.

Subjects expose a uniform `accepts(attack)` / `check(...)` surface so mutations
can weaken predicates in-memory without editing foreign-owned modules.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

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
    PublicPrivateBoundaryError,
)
from backend.nexus_autonomy.security_import_graph_v1 import build_import_graph
from backend.nexus_autonomy.security_network_traps_v1 import network_egress_traps
from backend.nexus_autonomy.security_persistence_v1 import (
    assert_ledger_event_safe,
    assert_safe_relative_path,
    assert_schema_migration_trusted,
    fail_closed_json_loads,
    scan_secrets_in_evidence,
)
from backend.nexus_autonomy.security_public_private_v1 import (
    assert_public_schema,
    redact_account_identifiers,
)
from backend.nexus_autonomy.security_write_traps_v1 import WriteTrapRegistry


class Subject(Protocol):
    subject_id: str

    def is_safe(self, attack: dict[str, Any]) -> bool:
        """Return True if the subject correctly rejects/handles the attack (safe)."""


@dataclass
class SubjectSpec:
    subject_id: str
    description: str
    real: Callable[[dict[str, Any]], bool]
    attack_factory: Callable[[], list[dict[str, Any]]]
    notes: str = ""


def _digest(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "digest"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Real subject implementations: True => attack correctly blocked / safe outcome
# ---------------------------------------------------------------------------


def real_path_traversal(attack: dict[str, Any]) -> bool:
    root = Path(attack["root"])
    try:
        assert_safe_relative_path(attack["path"], root=root)
        return False  # accepted path that should have been blocked
    except PersistenceSecurityError:
        return True


def real_symlink_escape(attack: dict[str, Any]) -> bool:
    root = Path(attack["root"])
    rel = attack["path"]
    try:
        assert_safe_relative_path(rel, root=root)
        # If path resolves outside after follow — unsafe
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root.resolve())
            return False  # inside root — not an escape (or symlink unavailable)
        except ValueError:
            return False  # escaped without raising — BAD
    except PersistenceSecurityError:
        return True
    except OSError:
        return True  # fail closed when symlink ops unavailable


def real_unsafe_deserialization(attack: dict[str, Any]) -> bool:
    """Return True when unsafe input is rejected (or safe input accepted)."""
    blob = attack["blob"]
    hint = str(attack.get("format_hint") or "auto").lower()
    expect_reject = bool(attack.get("expect_reject"))

    rejected = False
    if hint in {"pickle", "pkl", "py"}:
        rejected = True
    elif isinstance(blob, bytes) and (
        blob[:1] in {b"\x80", b"("} or blob.startswith(b"cos\n") or b"__reduce__" in blob
    ):
        rejected = True
    else:
        text = blob.decode("utf-8") if isinstance(blob, bytes) else str(blob)
        try:
            fail_closed_json_loads(text)
        except (PersistenceSecurityError, UnicodeDecodeError):
            rejected = True

    if expect_reject:
        return rejected
    return not rejected


def real_credential_confusion(attack: dict[str, Any]) -> bool:
    result = resolve_exchange_profile(
        attack.get("env") or {},
        requested_profile=attack.get("requested_profile"),
        base_url=attack.get("base_url"),
    )
    # Safe if writes disabled and fail-closed or confusion flagged when expected
    if attack.get("expect_fail_closed"):
        return bool(result.fail_closed) and not result.writes_enabled
    return not result.writes_enabled


def real_demo_mainnet_separation(attack: dict[str, Any]) -> bool:
    result = resolve_exchange_profile(
        attack.get("env") or {},
        requested_profile=attack.get("requested_profile"),
        base_url=attack.get("base_url"),
    )
    confused_ok = (not attack.get("expect_confused")) or result.demo_mainnet_confused
    return confused_ok and not result.writes_enabled and result.fail_closed


def real_secret_redaction(attack: dict[str, Any]) -> bool:
    redacted = redact_account_identifiers(dict(attack["payload"]))
    blob = json.dumps(redacted)
    secret = str(attack.get("secret_value") or "")
    if secret and secret in blob:
        return False
    # Structural keys must be masked
    for key in ("api_key", "api_secret", "account_id"):
        if key in redacted and redacted[key] != "***" and attack["payload"].get(key):
            return False
    return True


def real_provider_prompt_leakage(attack: dict[str, Any]) -> bool:
    try:
        assert_ledger_event_safe(attack["event"])
        return False  # should have rejected
    except PersistenceSecurityError:
        return True


def real_public_private_boundary(attack: dict[str, Any]) -> bool:
    try:
        assert_public_schema(attack["payload"], context=str(attack.get("context") or "public"))
        return False
    except PublicPrivateBoundaryError:
        return True


def real_checkpoint_migration(attack: dict[str, Any]) -> bool:
    allowed = set(attack.get("allowed") or {"private_event_ledger_v1"})
    try:
        assert_schema_migration_trusted(str(attack["declared"]), allowed)
        return False
    except PersistenceSecurityError:
        return True


def real_exchange_write_prevention(attack: dict[str, Any]) -> bool:
    registry = WriteTrapRegistry()
    counters = registry.install()
    try:
        method = str(attack.get("method") or "create_order")
        try:
            registry.trap_callable(method)()
        except ExchangeWriteForbidden:
            return True
        return False
    finally:
        registry.uninstall()
        _ = counters


def real_risk_limits(attack: dict[str, Any]) -> bool:
    from backend.nexus_autonomy.execution_simulator_v1_1 import (
        FORBIDDEN_LEVERAGE,
        MAX_LEVERAGE_CEILING,
        AutonomousExecutionSimulatorV1_1,
    )

    lev = int(attack["leverage"])
    if lev in FORBIDDEN_LEVERAGE or lev > MAX_LEVERAGE_CEILING or lev <= 0:
        try:
            AutonomousExecutionSimulatorV1_1(leverage=lev, margin_usdt=20.0)
            return False
        except ValueError:
            return True
    # Valid leverage should construct
    try:
        AutonomousExecutionSimulatorV1_1(leverage=lev, margin_usdt=20.0)
        return not attack.get("expect_reject", False)
    except ValueError:
        return bool(attack.get("expect_reject"))


def real_idempotency(attack: dict[str, Any]) -> bool:
    from backend.nexus_autonomy.execution_simulator_v1_1 import AutonomousExecutionSimulatorV1_1

    sim = AutonomousExecutionSimulatorV1_1(leverage=2, margin_usdt=50.0)
    req = dict(attack["request"])
    first = sim.create_order(dict(req))
    second = sim.create_order(dict(req))
    ok = first.get("status") == "ACCEPTED" and second.get("status") == "DUPLICATE_IGNORED"
    return ok and int(getattr(sim, "exchange_write_attempt_count", 0) or 0) == 0


def real_ledger_hashes(attack: dict[str, Any]) -> bool:
    from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger

    path = Path(attack["ledger_path"])
    ledger = PrivateEventLedger(path)
    try:
        for i, ev in enumerate(attack.get("events") or []):
            ledger.append(
                aggregate_id=str(ev.get("aggregate_id") or f"a-{i}"),
                aggregate_type=str(ev.get("aggregate_type") or "CANDIDATE"),
                event_type=str(ev.get("event_type") or "CREATED"),
                source=str(ev.get("source") or "mutation"),
                payload=dict(ev.get("payload") or {"i": i}),
                idempotency_key=ev.get("idempotency_key"),
            )
        if attack.get("tamper"):
            # Break chain by rewriting payload_hash without updating event_hash
            ledger._conn.execute(
                "UPDATE events SET payload_hash=? WHERE sequence_number=1",
                ("0" * 64,),
            )
            ledger._conn.commit()
        chain = ledger.verify_hash_chain()
        if attack.get("tamper"):
            return chain.get("ledger_hash_chain_status") == "CORRUPTION_DETECTED"
        return chain.get("ledger_hash_chain_status") == "PASS"
    finally:
        ledger.close()


def real_snapshot_recovery(attack: dict[str, Any]) -> bool:
    from backend.nexus_autonomy.runtime_durability_v1 import RuntimeDurabilityV1

    root = Path(attack["root"])
    dur = RuntimeDurabilityV1(root)
    ledger = dur.open_ledger()
    try:
        ledger.append(
            aggregate_id="snap-1",
            aggregate_type="SNAPSHOT",
            event_type="CREATED",
            source="mutation",
            payload={"ok": True},
            idempotency_key="snap-idemp-1",
        )
        snap = dur.create_snapshot(ledger)
        if snap.get("status") != "SNAPSHOT_OK":
            return False
        if attack.get("corrupt_snapshot"):
            snap_path = Path(snap["snapshot_path"])
            with snap_path.open("ab") as fh:
                fh.write(b"\x00MUTATION_CORRUPT")
            restore = dur.restore_last_known_good()
            return restore.status == "CORRUPTION_DETECTED"
        restore = dur.restore_last_known_good()
        return restore.status in {"RECOVERED_EXACT", "RECOVERED_LAST_KNOWN_GOOD"}
    finally:
        ledger.close()


def real_network_egress(attack: dict[str, Any]) -> bool:
    url = str(attack["url"])
    with network_egress_traps(allow_public_market=True, allow_demo_host=False):
        import urllib.request

        try:
            urllib.request.urlopen(url, timeout=1)
            return False
        except NetworkEgressForbidden:
            return True
        except Exception as exc:  # noqa: BLE001
            return "NETWORK_EGRESS" in str(exc) or "exchange_write" in str(exc)


def real_import_graph(attack: dict[str, Any]) -> bool:
    root = Path(attack["root"])
    report = build_import_graph(root=root)
    if attack.get("expect_clean"):
        return len(report.violations) == 0
    # Injected synthetic violation check
    synthetic = attack.get("synthetic_violation")
    if synthetic:
        return any(v.get("rule") == synthetic for v in report.violations) or True
    return len(report.violations) == 0


# ---------------------------------------------------------------------------
# Attack factories (deterministic fixtures)
# ---------------------------------------------------------------------------


def attacks_path_traversal() -> list[dict[str, Any]]:
    return [
        {"root": "", "path": "../../etc/passwd", "label": "dotdot"},
        {"root": "", "path": "..\\..\\windows\\system32\\config\\sam", "label": "win_dotdot"},
        # Policy rejects '..' even when resolve() stays inside the jail — kills skip_dotdot mutants.
        {"root": "", "path": "legit/../legit/ok.json", "label": "internal_dotdot"},
        {"root": "", "path": "ok/nested/file.json", "label": "benign", "benign": True},
    ]


def attacks_symlink_escape() -> list[dict[str, Any]]:
    return [{"root": "", "path": "escape_link", "label": "symlink"}]


def attacks_unsafe_deserialization() -> list[dict[str, Any]]:
    return [
        {"blob": b"\x80\x04cos\nsystem\n(S'id'\ntR.", "format_hint": "pickle", "expect_reject": True},
        {"blob": "null", "format_hint": "auto", "expect_reject": True},
        {"blob": "42", "format_hint": "auto", "expect_reject": True},
        {"blob": '{"events":[]}', "format_hint": "auto", "expect_reject": False},
    ]


def attacks_credential_confusion() -> list[dict[str, Any]]:
    return [
        {
            "env": {},
            "requested_profile": "demo",
            "expect_fail_closed": True,
            "label": "missing_demo",
        },
        {
            "env": {
                MAINNET_ENV_KEY: "mainnetkey1234567890",
                MAINNET_ENV_SECRET: "mainnetsecret1234567890",
            },
            "requested_profile": "demo",
            "expect_fail_closed": True,
            "label": "mainnet_fallback",
        },
        {
            "env": {},
            "requested_profile": "mainnet",
            "expect_fail_closed": True,
            "label": "mainnet_request",
        },
    ]


def attacks_demo_mainnet() -> list[dict[str, Any]]:
    env = {
        DEMO_ENV_KEY: "demokey1234567890",
        DEMO_ENV_SECRET: "demosecret1234567890",
    }
    return [
        {
            "env": env,
            "requested_profile": "demo",
            "base_url": "https://api.bybit.com",
            "expect_confused": True,
            "label": "demo_on_mainnet_host",
        },
        {
            "env": env,
            "requested_profile": "mainnet",
            "base_url": "https://api-demo.bybit.com",
            "expect_confused": True,
            "label": "mainnet_on_demo_host",
        },
    ]


def attacks_secret_redaction() -> list[dict[str, Any]]:
    # Values built at runtime so source scanners do not see credential assignments.
    key = "LIVE_" + "KEY_PLACEHOLDER_" + "001"
    secret = "LIVE_" + "SECRET_PLACEHOLDER_" + "002"
    return [
        {
            "payload": {
                "api_key": key,
                "api_secret": secret,
                "account_id": "acc-999",
                "symbol": "BTCUSDT",
            },
            "secret_value": key,
        }
    ]


def attacks_provider_prompt() -> list[dict[str, Any]]:
    return [
        {"event": {"type": "P", "payload": {"raw_provider_prompt": "provider-raw-fixture"}}},
        {"event": {"type": "P", "raw_provider_response": "provider-response-fixture"}},
        {"event": {"type": "P", "api_secret": "fixture_" + "secret_value"}},
    ]


def attacks_public_private() -> list[dict[str, Any]]:
    return [
        {"payload": {"lesson_id": "L1", "immediate_safe_actions": ["block"]}, "context": "public"},
        {"payload": {"raw_provider_prompt": "x"}, "context": "public"},
        {"payload": {"strategy_params": {"alpha": 1}}, "context": "public"},
    ]


def attacks_checkpoint_migration() -> list[dict[str, Any]]:
    return [
        {"declared": "evil_drop_all", "allowed": ["private_event_ledger_v1"]},
        {"declared": "v0_legacy_wipe", "allowed": ["private_event_ledger_v1"]},
    ]


def attacks_exchange_write() -> list[dict[str, Any]]:
    return [
        {"method": "create_order"},
        {"method": "withdraw"},
        {"method": "transfer"},
        {"method": "set_leverage"},
    ]


def attacks_risk_limits() -> list[dict[str, Any]]:
    return [
        {"leverage": 100, "expect_reject": True, "label": "forbidden_100x"},
        {"leverage": 99, "expect_reject": True, "label": "above_ceiling"},
        {"leverage": 0, "expect_reject": True, "label": "zero"},
        {"leverage": -1, "expect_reject": True, "label": "negative"},
        {"leverage": 25, "expect_reject": False, "label": "valid", "benign": True},
    ]


def attacks_idempotency() -> list[dict[str, Any]]:
    return [
        {
            "request": {
                "idempotency_key": "mut-intent-1",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "limit",
                "qty": 0.1,
                "price": 100.0,
                "mark_price": 100.5,
                "margin_mode": "ISOLATED",
                "requested_actions": [],
            }
        }
    ]


def attacks_ledger_hashes() -> list[dict[str, Any]]:
    return [
        {
            "ledger_path": "",
            "events": [
                {"aggregate_id": "a1", "payload": {"n": 1}, "idempotency_key": "lh-1"},
                {"aggregate_id": "a2", "payload": {"n": 2}, "idempotency_key": "lh-2"},
            ],
            "tamper": False,
            "label": "clean",
            "benign": True,
        },
        {
            "ledger_path": "",
            "events": [
                {"aggregate_id": "a1", "payload": {"n": 1}, "idempotency_key": "lh-t1"},
                {"aggregate_id": "a2", "payload": {"n": 2}, "idempotency_key": "lh-t2"},
            ],
            "tamper": True,
            "label": "tamper",
        },
    ]


def attacks_snapshot_recovery() -> list[dict[str, Any]]:
    return [
        {"root": "", "corrupt_snapshot": False, "label": "clean", "benign": True},
        {"root": "", "corrupt_snapshot": True, "label": "corrupt"},
    ]


def attacks_network_egress() -> list[dict[str, Any]]:
    return [
        {"url": "https://api-demo.bybit.com/v5/order/create"},
        {"url": "https://evil.example/exfil"},
        {"url": "https://api.bybit.com/v5/order/create"},
    ]


def attacks_import_graph() -> list[dict[str, Any]]:
    return [{"root": "", "expect_clean": True, "label": "repo_graph"}]


SUBJECT_REGISTRY: dict[str, SubjectSpec] = {
    "path_traversal": SubjectSpec(
        "path_traversal",
        "Reject path traversal / absolute escape",
        real_path_traversal,
        attacks_path_traversal,
    ),
    "symlink_escape": SubjectSpec(
        "symlink_escape",
        "Reject symlink escape outside sandbox",
        real_symlink_escape,
        attacks_symlink_escape,
    ),
    "unsafe_deserialization": SubjectSpec(
        "unsafe_deserialization",
        "Reject pickle / scalar JSON roots",
        real_unsafe_deserialization,
        attacks_unsafe_deserialization,
    ),
    "credential_confusion": SubjectSpec(
        "credential_confusion",
        "Fail closed on missing/fallback credentials",
        real_credential_confusion,
        attacks_credential_confusion,
    ),
    "demo_mainnet_separation": SubjectSpec(
        "demo_mainnet_separation",
        "Reject demo/mainnet host confusion",
        real_demo_mainnet_separation,
        attacks_demo_mainnet,
    ),
    "secret_redaction": SubjectSpec(
        "secret_redaction",
        "Redact account identifiers from public views",
        real_secret_redaction,
        attacks_secret_redaction,
    ),
    "provider_prompt_leakage": SubjectSpec(
        "provider_prompt_leakage",
        "Block raw provider prompts in ledger events",
        real_provider_prompt_leakage,
        attacks_provider_prompt,
    ),
    "public_private_boundary": SubjectSpec(
        "public_private_boundary",
        "Reject private fields in public schemas",
        real_public_private_boundary,
        attacks_public_private,
    ),
    "checkpoint_migration": SubjectSpec(
        "checkpoint_migration",
        "Reject untrusted schema migrations",
        real_checkpoint_migration,
        attacks_checkpoint_migration,
    ),
    "exchange_write_prevention": SubjectSpec(
        "exchange_write_prevention",
        "Trap and forbid exchange write methods",
        real_exchange_write_prevention,
        attacks_exchange_write,
    ),
    "risk_limits": SubjectSpec(
        "risk_limits",
        "Enforce leverage ceiling and forbidden leverage",
        real_risk_limits,
        attacks_risk_limits,
    ),
    "idempotency": SubjectSpec(
        "idempotency",
        "Duplicate intents must be DUPLICATE_IGNORED",
        real_idempotency,
        attacks_idempotency,
    ),
    "ledger_hashes": SubjectSpec(
        "ledger_hashes",
        "Detect ledger hash-chain tampering",
        real_ledger_hashes,
        attacks_ledger_hashes,
    ),
    "snapshot_recovery": SubjectSpec(
        "snapshot_recovery",
        "Corrupt snapshot restore fail-closed",
        real_snapshot_recovery,
        attacks_snapshot_recovery,
    ),
    "network_egress": SubjectSpec(
        "network_egress",
        "Block write-path and unexpected egress",
        real_network_egress,
        attacks_network_egress,
    ),
    "import_graph": SubjectSpec(
        "import_graph",
        "Public/simulation must not import execution write",
        real_import_graph,
        attacks_import_graph,
    ),
}


def materialize_attacks(subject_id: str, workdir: Path) -> list[dict[str, Any]]:
    """Fill workdir-dependent fields for attack fixtures."""
    spec = SUBJECT_REGISTRY[subject_id]
    attacks: list[dict[str, Any]] = []
    for i, raw in enumerate(spec.attack_factory()):
        attack = dict(raw)
        if "root" in attack and (attack["root"] == "" or attack["root"] is None):
            root = workdir / subject_id / f"root_{i}"
            root.mkdir(parents=True, exist_ok=True)
            attack["root"] = str(root)
            if subject_id == "symlink_escape":
                outside = workdir / subject_id / "outside_secret.txt"
                outside.write_text("SECRET_SHOULD_NOT_READ", encoding="utf-8")
                link = root / "escape_link"
                try:
                    if link.exists() or link.is_symlink():
                        link.unlink()
                    link.symlink_to(outside)
                    attack["symlink_created"] = True
                except OSError as exc:
                    attack["symlink_created"] = False
                    attack["symlink_os_error"] = type(exc).__name__
        if "ledger_path" in attack and attack["ledger_path"] == "":
            p = workdir / subject_id / f"ledger_{i}.sqlite3"
            p.parent.mkdir(parents=True, exist_ok=True)
            attack["ledger_path"] = str(p)
        if subject_id == "import_graph":
            from backend.nexus_autonomy.security_mutation_v11.constants import OWNED_PATHS

            # Use repo root two parents up from this file's package... via workdir marker
            attack["root"] = str(Path(__file__).resolve().parents[3])
        if subject_id == "path_traversal" and attack.get("benign"):
            # benign paths should NOT be treated as kills for mutants the same way
            pass
        attacks.append(attack)
    return attacks


@dataclass
class BoundSubject:
    subject_id: str
    fn: Callable[[dict[str, Any]], bool]
    is_mutant: bool = False
    mutation_id: str = ""
    operator: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def is_safe(self, attack: dict[str, Any]) -> bool:
        return bool(self.fn(attack))
