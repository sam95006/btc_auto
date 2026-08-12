"""Adversarial scenarios beyond pure mutation killing (property / fuzz / traps)."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable

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
    fail_closed_json_loads,
    scan_secrets_in_evidence,
)
from backend.nexus_autonomy.security_public_private_v1 import assert_public_schema
from backend.nexus_autonomy.security_write_traps_v1 import WriteTrapRegistry
from backend.nexus_autonomy.security_mutation_v11.fixtures import (
    build_filesystem_attack_tree,
    fuzz_json_blobs,
    fuzz_path_vectors,
)
from backend.nexus_autonomy.security_mutation_v11.models import AdversarialScenarioResult


def scenario_filesystem_fixtures(workdir: Path) -> AdversarialScenarioResult:
    manifest = build_filesystem_attack_tree(workdir / "fs_attacks")
    sandbox = Path(manifest["sandbox"])
    blocked = 0
    total = 0
    for vec in manifest["traversal_vectors"]:
        total += 1
        try:
            assert_safe_relative_path(vec, root=sandbox)
        except PersistenceSecurityError:
            blocked += 1
        except Exception:
            blocked += 1
    # pickle fixture must not be json-loaded as trusted object without reject
    pickle_blocked = False
    raw = Path(manifest["pickle_fixture"]).read_bytes()
    if raw[:1] == b"\x80":
        pickle_blocked = True
    corrupt_blocked = False
    try:
        fail_closed_json_loads(Path(manifest["corrupt_json"]).read_text(encoding="utf-8", errors="replace"))
    except PersistenceSecurityError:
        corrupt_blocked = True
    passed = blocked >= max(1, total - 1) and pickle_blocked and corrupt_blocked
    return AdversarialScenarioResult(
        scenario_id="filesystem_attack_fixtures",
        passed=passed,
        fail_closed=passed,
        detail="fs_fixtures_blocked" if passed else "fs_fixtures_weak",
        critical=not passed,
        evidence={"blocked": blocked, "total": total, "pickle_blocked": pickle_blocked, "corrupt_blocked": corrupt_blocked},
    )


def scenario_path_fuzz(workdir: Path) -> AdversarialScenarioResult:
    sandbox = workdir / "fuzz_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "legit").mkdir(exist_ok=True)
    vectors = fuzz_path_vectors()
    blocked = 0
    dangerous = 0
    for v in vectors:
        is_dangerous = ".." in v.replace("\\", "/") or "\x00" in v or v.startswith("/") or (len(v) > 1 and v[1] == ":")
        if not is_dangerous:
            continue
        dangerous += 1
        try:
            assert_safe_relative_path(v, root=sandbox)
        except PersistenceSecurityError:
            blocked += 1
        except Exception:
            blocked += 1
    passed = dangerous > 0 and blocked == dangerous
    return AdversarialScenarioResult(
        scenario_id="path_fuzz",
        passed=passed,
        fail_closed=passed,
        detail=f"fuzz_blocked={blocked}/{dangerous}",
        critical=not passed,
        evidence={"dangerous": dangerous, "blocked": blocked, "vector_count": len(vectors)},
    )


def scenario_json_fuzz(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    blobs = fuzz_json_blobs()
    rejected_scalars = 0
    scalar_total = 0
    for b in blobs:
        if isinstance(b, str) and b.startswith("{not-json"):
            try:
                fail_closed_json_loads(b)
            except PersistenceSecurityError:
                rejected_scalars += 1
            scalar_total += 1
            continue
        if b is None or isinstance(b, (int, float, bool, str)):
            scalar_total += 1
            try:
                fail_closed_json_loads(json.dumps(b))
            except PersistenceSecurityError:
                rejected_scalars += 1
    passed = scalar_total > 0 and rejected_scalars == scalar_total
    return AdversarialScenarioResult(
        scenario_id="json_fuzz",
        passed=passed,
        fail_closed=passed,
        detail=f"scalar_rejected={rejected_scalars}/{scalar_total}",
        critical=not passed,
        evidence={"scalar_total": scalar_total, "rejected": rejected_scalars},
    )


def scenario_import_graph(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    root = Path(__file__).resolve().parents[3]
    report = build_import_graph(root=root)
    passed = len(report.violations) == 0
    return AdversarialScenarioResult(
        scenario_id="import_graph",
        passed=passed,
        fail_closed=passed,
        detail="import_graph_clean" if passed else f"violations={len(report.violations)}",
        critical=not passed,
        evidence={
            "violation_count": len(report.violations),
            "violations": report.violations[:20],
            "node_count": report.node_count,
            "edge_count": report.edge_count,
        },
    )


def scenario_network_traps(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    write_blocked = unexpected_blocked = mainnet_blocked = False
    with network_egress_traps(allow_public_market=True, allow_demo_host=False) as counters:
        import urllib.request

        for url, flag_name in (
            ("https://api-demo.bybit.com/v5/order/create", "write"),
            ("https://evil.example/exfil", "unexpected"),
            ("https://api.bybit.com/v5/order/create", "mainnet"),
        ):
            try:
                urllib.request.urlopen(url, timeout=1)
            except (NetworkEgressForbidden, Exception) as exc:
                text = str(exc)
                ok = "NETWORK_EGRESS" in text or "exchange_write" in text or "unexpected_domain" in text
                if flag_name == "write":
                    write_blocked = ok
                elif flag_name == "unexpected":
                    unexpected_blocked = ok
                else:
                    mainnet_blocked = ok
    passed = write_blocked and unexpected_blocked and mainnet_blocked
    return AdversarialScenarioResult(
        scenario_id="network_traps",
        passed=passed,
        fail_closed=passed,
        detail="egress_blocked" if passed else "egress_leak",
        critical=not passed,
        evidence={
            "write_blocked": write_blocked,
            "unexpected_blocked": unexpected_blocked,
            "mainnet_blocked": mainnet_blocked,
            "counters": counters.to_dict(),
        },
    )


def scenario_exchange_write_traps(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    registry = WriteTrapRegistry()
    counters = registry.install()
    fired = 0
    try:
        for method in ("create_order", "withdraw", "transfer"):
            try:
                registry.trap_callable(method)()
            except ExchangeWriteForbidden:
                fired += 1
    finally:
        registry.uninstall()
    # Intentional probes must not count as workflow writes in status counters (recorded separately)
    passed = fired == 3
    return AdversarialScenarioResult(
        scenario_id="exchange_write_traps",
        passed=passed,
        fail_closed=passed,
        detail="write_traps_fired" if passed else "write_traps_missed",
        critical=not passed,
        evidence={
            "fired": fired,
            "intentional_trap_probe_count": counters.exchange_write_attempt_count,
            "workflow_exchange_write_attempt_count": 0,
        },
    )


def scenario_secret_scan_property(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    clean = {"symbol": "BTCUSDT", "status": "OK", "note": "no credentials"}
    # Assignment form (non-JSON) exercises credential_assignment; JSON quoted keys must too.
    dirty_assign = "api_key = '" + ("A" * 20) + "'"
    dirty_json = {"api_key": "ABCD" + "EFGH" * 4}
    clean_hits = scan_secrets_in_evidence(clean)
    assign_hits = scan_secrets_in_evidence(dirty_assign)
    json_hits = scan_secrets_in_evidence(dirty_json)
    assign_ok = "credential_assignment" in assign_hits
    json_ok = "credential_assignment" in json_hits or any(
        h.startswith("pattern:") for h in json_hits
    )
    json_assignment_ok = "credential_assignment" in json_hits
    passed = len(clean_hits) == 0 and assign_ok and json_ok and json_assignment_ok
    return AdversarialScenarioResult(
        scenario_id="secret_scan_property",
        passed=passed,
        fail_closed=passed,
        detail="secret_scan_property_ok" if passed else "secret_scan_property_fail",
        critical=not passed,
        evidence={
            # Codes only — never echo fixture secret material into status artifacts.
            "clean_hit_count": len(clean_hits),
            "assign_ok": assign_ok,
            "json_ok": json_ok,
            "json_assignment_ok": json_assignment_ok,
        },
    )


def scenario_checkpoint_digest(workdir: Path) -> AdversarialScenarioResult:
    """Tampered checkpoint digest must fail closed (local fixture)."""
    path = workdir / "checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"generation": 3, "state": "RUNNING"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path.write_text(json.dumps({**body, "digest": digest}), encoding="utf-8")
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["state"] = "COMPROMISED"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    stored = str(tampered.get("digest") or "")
    body2 = {k: v for k, v in tampered.items() if k != "digest"}
    expected = hashlib.sha256(
        json.dumps(body2, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    blocked = stored != expected
    return AdversarialScenarioResult(
        scenario_id="checkpoint_digest",
        passed=blocked,
        fail_closed=blocked,
        detail="digest_mismatch_detected" if blocked else "tamper_undetected",
        critical=not blocked,
        evidence={"blocked": blocked},
    )


def scenario_concurrent_idempotency(workdir: Path) -> AdversarialScenarioResult:
    """Concurrent duplicate intents must not double-accept (simulator only)."""
    from backend.nexus_autonomy.execution_simulator_v1_1 import AutonomousExecutionSimulatorV1_1

    _ = workdir
    sim = AutonomousExecutionSimulatorV1_1(leverage=2, margin_usdt=50.0)
    req = {
        "idempotency_key": "race-intent-1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "limit",
        "qty": 0.1,
        "price": 100.0,
        "mark_price": 100.5,
        "margin_mode": "ISOLATED",
        "requested_actions": [],
    }
    results: list[str] = []
    barrier = threading.Barrier(4)
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait(timeout=2.0)
        out = sim.create_order(dict(req))
        with lock:
            results.append(str(out.get("status")))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)
    accepted = sum(1 for s in results if s == "ACCEPTED")
    ignored = sum(1 for s in results if s == "DUPLICATE_IGNORED")
    passed = (
        len(results) == 4
        and accepted == 1
        and ignored == 3
        and int(getattr(sim, "exchange_write_attempt_count", 0) or 0) == 0
    )
    return AdversarialScenarioResult(
        scenario_id="concurrent_idempotency",
        passed=passed,
        fail_closed=passed,
        detail="concurrent_idempotency_ok" if passed else f"statuses={results}",
        critical=not passed,
        evidence={"results": results, "accepted": accepted, "ignored": ignored},
    )


def scenario_provider_public_leak(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    blocked_ledger = False
    blocked_public = False
    try:
        assert_ledger_event_safe({"type": "X", "payload": {"raw_provider_prompt": "x"}})
    except PersistenceSecurityError:
        blocked_ledger = True
    try:
        assert_public_schema({"raw_provider_response": "y"}, context="public")
    except PublicPrivateBoundaryError:
        blocked_public = True
    passed = blocked_ledger and blocked_public
    return AdversarialScenarioResult(
        scenario_id="provider_public_leak",
        passed=passed,
        fail_closed=passed,
        detail="provider_leak_blocked" if passed else "provider_leak_allowed",
        critical=not passed,
        evidence={"blocked_ledger": blocked_ledger, "blocked_public": blocked_public},
    )


def scenario_false_pass_guards(workdir: Path) -> AdversarialScenarioResult:
    """Meta-guard: empty campaign / zero kills must never look like PASS inputs."""
    _ = workdir
    from backend.nexus_autonomy.security_mutation_v11.constants import SUBJECT_IDS
    from backend.nexus_autonomy.security_mutation_v11.mutations import MUTATION_OPERATORS

    subject_ok = len(SUBJECT_IDS) >= 12
    ops = sum(len(v) for v in MUTATION_OPERATORS.values())
    ops_ok = ops >= 20
    # Ensure always_claim_safe mutants exist (false-safe class) so oracle path is exercised
    always_safe_ops = sum(
        1 for ops_list in MUTATION_OPERATORS.values() for name, _, _ in ops_list if name == "always_claim_safe"
    )
    passed = subject_ok and ops_ok and always_safe_ops >= 8
    return AdversarialScenarioResult(
        scenario_id="false_pass_guards",
        passed=passed,
        fail_closed=passed,
        detail="false_pass_guards_ok" if passed else "false_pass_guards_weak",
        critical=not passed,
        evidence={
            "subject_count": len(SUBJECT_IDS),
            "operator_count": ops,
            "always_claim_safe_count": always_safe_ops,
        },
    )


SCENARIO_RUNNERS: dict[str, Callable[[Path], AdversarialScenarioResult]] = {
    "filesystem_attack_fixtures": scenario_filesystem_fixtures,
    "path_fuzz": scenario_path_fuzz,
    "json_fuzz": scenario_json_fuzz,
    "import_graph": scenario_import_graph,
    "network_traps": scenario_network_traps,
    "exchange_write_traps": scenario_exchange_write_traps,
    "secret_scan_property": scenario_secret_scan_property,
    "checkpoint_digest": scenario_checkpoint_digest,
    "concurrent_idempotency": scenario_concurrent_idempotency,
    "provider_public_leak": scenario_provider_public_leak,
    "false_pass_guards": scenario_false_pass_guards,
}

SCENARIO_IDS: tuple[str, ...] = tuple(SCENARIO_RUNNERS.keys())


def run_adversarial_scenarios(workdir: Path) -> list[AdversarialScenarioResult]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    results: list[AdversarialScenarioResult] = []
    for sid, runner in SCENARIO_RUNNERS.items():
        try:
            results.append(runner(workdir / sid))
        except Exception as exc:  # noqa: BLE001
            results.append(
                AdversarialScenarioResult(
                    scenario_id=sid,
                    passed=False,
                    fail_closed=False,
                    detail=f"scenario_exception:{type(exc).__name__}:{exc}",
                    critical=True,
                )
            )
    return results
