"""V16-H Decision Memory Graph — Pass 1 core + Pass 2 adversarial + Pass 3 breaks."""
from __future__ import annotations

import pytest

from backend.nexus_decision_memory_graph import (
    EDGE_KINDS,
    HARD_BANS,
    NODE_KINDS,
    DecisionMemoryGraph,
    DecisionMemoryGraphError,
    HardBanViolation,
    InMemoryGraphStorage,
    build_linked_decision_fixture,
    build_similarity_query,
    hard_ban_probe_matrix,
    is_fail_safe,
    project_node_public,
    schema_manifest,
    unavailable_response,
    validate_similarity_query,
)
from backend.nexus_decision_memory_graph.constants import PRIVATE_FIELD_NAMES, PUBLIC_SAFE_PAYLOAD_KEYS
from backend.nexus_decision_memory_graph.hard_bans import refuse_status_json
from backend.nexus_decision_memory_graph.public_projection import assert_no_private_leak
from backend.nexus_decision_memory_graph.schema import SchemaError, validate_node_record
from backend.nexus_decision_memory_graph.secrets import assert_no_secrets, scan_for_secrets
from backend.nexus_decision_memory_graph.similarity import SimilarityQueryError


# ---------------------------------------------------------------------------
# Pass 1 — core contract
# ---------------------------------------------------------------------------


def test_schema_manifest_versioned() -> None:
    m = schema_manifest()
    assert m["schema_version"] == 1
    assert m["versioned"] is True
    assert set(NODE_KINDS).issuperset(
        {
            "MARKET_SNAPSHOT",
            "SYMBOL",
            "REGIME",
            "CANDIDATE",
            "STRATEGY_EXPERT",
            "REASONER",
            "CRITIC",
            "SUPPORTING_EVIDENCE",
            "CONTRADICTING_EVIDENCE",
            "RISK_DECISION",
            "ENTRY",
            "EXIT",
            "COSTS",
            "OUTCOME",
            "ERROR_CLASSIFICATION",
            "REFLECTION",
            "LESSON",
            "COUNTERFACTUAL",
            "VALIDATION",
            "CODE_VERSION",
            "MODEL_VERSION",
            "POLICY_VERSION",
        }
    )
    assert "SUPPORTED_BY" in EDGE_KINDS
    assert "CONTRADICTED_BY" in EDGE_KINDS


def test_linked_fixture_seals_all_kinds() -> None:
    fx = build_linked_decision_fixture()
    kinds = {n["kind"] for n in fx["nodes"].values()}
    required = {
        "MARKET_SNAPSHOT",
        "SYMBOL",
        "REGIME",
        "CANDIDATE",
        "STRATEGY_EXPERT",
        "REASONER",
        "CRITIC",
        "SUPPORTING_EVIDENCE",
        "CONTRADICTING_EVIDENCE",
        "RISK_DECISION",
        "ENTRY",
        "EXIT",
        "COSTS",
        "OUTCOME",
        "ERROR_CLASSIFICATION",
        "REFLECTION",
        "LESSON",
        "COUNTERFACTUAL",
        "VALIDATION",
        "CODE_VERSION",
        "MODEL_VERSION",
        "POLICY_VERSION",
        "DECISION",
    }
    assert required.issubset(kinds)
    assert len(fx["edges"]) >= 20
    for node in fx["nodes"].values():
        assert node["immutable"] is True
        assert node["pit_bound"] is True
        assert len(node["lineage_hash"]) == 64
        assert node["node_id"].startswith("dmg_")


def test_immutable_ids_and_duplicate_reject() -> None:
    g = DecisionMemoryGraph()
    n = g.seal_node(kind="SYMBOL", as_of_ms=100, payload={"symbol": "ETHUSDT", "label": "ETHUSDT"})
    with pytest.raises(DecisionMemoryGraphError, match="immutable_duplicate"):
        g.seal_node(
            kind="SYMBOL",
            as_of_ms=100,
            payload={"symbol": "ETHUSDT", "label": "ETHUSDT"},
            node_id=n["node_id"],
        )
    with pytest.raises(DecisionMemoryGraphError, match="mutation_forbidden"):
        g.update_node(n["node_id"], {})
    with pytest.raises(DecisionMemoryGraphError, match="deletion_forbidden"):
        g.delete_node(n["node_id"])


def test_pit_lookup_excludes_future() -> None:
    fx = build_linked_decision_fixture(as_of_ms=1_000)
    g: DecisionMemoryGraph = fx["graph"]
    # Seal a future node after the decision chain base time.
    future = g.seal_node(
        kind="OUTCOME",
        as_of_ms=9_999,
        payload={"outcome_class": "FUTURE_ONLY", "data_class": "FIXTURE"},
    )
    pit = g.pit_lookup(as_of_ms=1_006)
    assert pit["ok"] is True
    assert pit["pit_bound"] is True
    assert pit["future_leakage"] is False
    ids = {n["node_id"] for n in pit["nodes"]}
    assert future["node_id"] not in ids
    assert all(n["as_of_ms"] <= 1_006 for n in pit["nodes"])
    assert all(e["as_of_ms"] <= 1_006 for e in pit["edges"])


def test_lineage_hash_stable_and_parent_bound() -> None:
    g = DecisionMemoryGraph()
    a = g.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "BTCUSDT", "label": "BTCUSDT"})
    b1 = g.seal_node(
        kind="MARKET_SNAPSHOT",
        as_of_ms=1,
        payload={"symbol": "BTCUSDT", "summary": "s"},
        parent_lineage_hashes=[a["lineage_hash"]],
    )
    g2 = DecisionMemoryGraph()
    a2 = g2.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "BTCUSDT", "label": "BTCUSDT"})
    b2 = g2.seal_node(
        kind="MARKET_SNAPSHOT",
        as_of_ms=1,
        payload={"symbol": "BTCUSDT", "summary": "s"},
        parent_lineage_hashes=[a2["lineage_hash"]],
    )
    assert a["lineage_hash"] == a2["lineage_hash"]
    assert b1["lineage_hash"] == b2["lineage_hash"]
    # Different parent lineage changes child seal.
    other = g.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "ETHUSDT", "label": "ETHUSDT"})
    b3 = g.seal_node(
        kind="MARKET_SNAPSHOT",
        as_of_ms=1,
        payload={"symbol": "BTCUSDT", "summary": "s"},
        parent_lineage_hashes=[other["lineage_hash"]],
        node_id="dmg_forced_diff_parent",
    )
    assert b3["lineage_hash"] != b1["lineage_hash"]


def test_similarity_query_contract_pit() -> None:
    fx = build_linked_decision_fixture(as_of_ms=2_000)
    g: DecisionMemoryGraph = fx["graph"]
    # Second decision-like node for overlap.
    g.seal_node(
        kind="DECISION",
        as_of_ms=2_000,
        payload={
            "status": "HISTORICAL_REPLAY",
            "recommendation": "WAIT",
            "symbol": "BTCUSDT",
            "similarity_tags": ["btc", "trend"],
            "data_class": "FIXTURE",
        },
        node_id="dmg_decision_similar_peer",
    )
    out = g.similarity_query(
        query_id="q1",
        as_of_ms=2_000,
        anchor_node_id=fx["decision"]["node_id"],
        dimensions={"similarity_tags": 1.0, "symbol": 1.0},
        limit=5,
    )
    assert out["ok"] is True
    assert out["pit_bound"] is True
    assert out["ranking_claim"] is False
    assert out["profitability_claim"] is False
    assert out["anchor_found"] is True
    validate_similarity_query(out["query"])
    # Future peer must not appear.
    g.seal_node(
        kind="DECISION",
        as_of_ms=99_000,
        payload={
            "status": "HISTORICAL_REPLAY",
            "recommendation": "WAIT",
            "symbol": "BTCUSDT",
            "similarity_tags": ["btc", "trend"],
            "data_class": "FIXTURE",
        },
        node_id="dmg_decision_future_peer",
    )
    out2 = g.similarity_query(
        query_id="q2",
        as_of_ms=2_000,
        anchor_node_id=fx["decision"]["node_id"],
        dimensions={"similarity_tags": 1.0},
        limit=10,
    )
    ids = {r["node_id"] for r in out2["results"]}
    assert "dmg_decision_future_peer" not in ids


def test_swappable_storage_no_external_db() -> None:
    store = InMemoryGraphStorage()
    g = DecisionMemoryGraph(storage=store)
    n = g.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "BTCUSDT", "label": "BTCUSDT"})
    assert store.get_node(n["node_id"]) is not None
    assert isinstance(store, InMemoryGraphStorage)


def test_public_projection_strips_private() -> None:
    g = DecisionMemoryGraph()
    # Private keys rejected at seal — inject via storage bypass for projection test.
    store = InMemoryGraphStorage()
    g2 = DecisionMemoryGraph(storage=store)
    clean = g2.seal_node(
        kind="REASONER",
        as_of_ms=1,
        payload={"summary": "ok", "recommendation": "WAIT", "data_class": "FIXTURE"},
    )
    # Manually plant a private field into a copy for projection defense.
    dirty = dict(clean)
    dirty["payload"] = {
        **clean["payload"],
        "api_key": "SHOULD_NOT_LEAK_1234567890",
        "founder_only_note": "secret note",
        "proprietary_threshold": 0.123,
    }
    pub = project_node_public(dirty)
    assert pub is not None
    assert "api_key" not in pub["payload"]
    assert "founder_only_note" not in pub["payload"]
    assert "proprietary_threshold" not in pub["payload"]
    assert pub["private_fields_included"] is False
    assert pub["raw_memory_graph"] is False
    assert_no_private_leak(pub)


# ---------------------------------------------------------------------------
# Pass 2 — adversarial hardening
# ---------------------------------------------------------------------------


def test_secret_storage_rejected() -> None:
    g = DecisionMemoryGraph()
    with pytest.raises(HardBanViolation, match="no_secret_storage"):
        g.seal_node(
            kind="REASONER",
            as_of_ms=1,
            payload={"summary": "x", "api_key": "REDACTED_TEST_CREDENTIAL_VALUE_001"},
        )
    scan = scan_for_secrets({"token": "abcdefghijklmnop"})
    assert scan["pass"] is False
    with pytest.raises(HardBanViolation):
        assert_no_secrets({"password": "supersecretvalue"})


def test_graph_unavailable_fail_safe() -> None:
    store = InMemoryGraphStorage()
    g = DecisionMemoryGraph(storage=store)
    g.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "BTCUSDT", "label": "BTCUSDT"})
    store.mark_unavailable()
    out = g.pit_lookup(as_of_ms=10)
    assert is_fail_safe(out)
    assert out["trading_allowed"] is False
    assert out["fail_open"] is False
    assert out["fabricated"] is False
    assert out["nodes"] == []
    sim = g.similarity_query(
        query_id="x",
        as_of_ms=10,
        anchor_node_id="missing",
        dimensions={"symbol": 1.0},
    )
    assert is_fail_safe(sim)
    seal = g.seal_node(kind="SYMBOL", as_of_ms=2, payload={"symbol": "ETHUSDT", "label": "ETHUSDT"})
    assert is_fail_safe(seal)


def test_hard_ban_probe_matrix_all_refused() -> None:
    matrix = hard_ban_probe_matrix()
    assert matrix["all_refused"] is True
    assert "no_private_field_leak_to_public" in HARD_BANS
    assert "no_required_external_graph_db" in HARD_BANS
    assert "no_status_json_lane_reports" in HARD_BANS
    with pytest.raises(HardBanViolation, match="no_status_json"):
        refuse_status_json()


def test_similarity_claims_forbidden() -> None:
    q = build_similarity_query(
        query_id="bad",
        as_of_ms=1,
        anchor_node_id="n1",
        dimensions={"symbol": 1.0},
    )
    q["ranking_claim"] = True
    with pytest.raises(SimilarityQueryError, match="claims_forbidden"):
        validate_similarity_query(q)


def test_schema_rejects_mutable_or_unknown_kind() -> None:
    bad = {
        "schema": "nexus_decision_memory_node_v16_h",
        "schema_version": 1,
        "node_id": "x",
        "kind": "NOT_A_KIND",
        "as_of_ms": 1,
        "payload": {},
        "lineage_hash": "a" * 64,
        "pit_bound": True,
        "immutable": True,
        "version_pins": {},
    }
    with pytest.raises(SchemaError, match="unknown_node_kind"):
        validate_node_record(bad)
    bad2 = dict(bad)
    bad2["kind"] = "SYMBOL"
    bad2["immutable"] = False
    with pytest.raises(SchemaError, match="must_be_immutable"):
        validate_node_record(bad2)


def test_edge_requires_existing_endpoints() -> None:
    g = DecisionMemoryGraph()
    a = g.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "BTCUSDT", "label": "BTCUSDT"})
    with pytest.raises(DecisionMemoryGraphError, match="edge_to_missing"):
        g.seal_edge(kind="OF_SYMBOL", from_id=a["node_id"], to_id="missing", as_of_ms=1)


def test_public_view_no_private_field_names() -> None:
    fx = build_linked_decision_fixture()
    pub = fx["graph"].public_view(as_of_ms=fx["as_of_ms"] + 100)
    assert pub.get("raw_memory_graph") is False
    blob = str(pub).lower()
    for name in ("api_key", "private_key", "wallet_seed", "exchange_credentials"):
        assert f"'{name}'" not in blob and f'"{name}"' not in blob
    assert_no_private_leak(pub)


# ---------------------------------------------------------------------------
# Pass 3 — independent break attempts
# ---------------------------------------------------------------------------


def test_break_force_future_into_pit_via_filter() -> None:
    """Even if a buggy caller passes mixed lists, pit_lookup asserts no future."""
    fx = build_linked_decision_fixture(as_of_ms=50)
    g: DecisionMemoryGraph = fx["graph"]
    pit = g.pit_lookup(as_of_ms=50)
    # Storage itself cannot return future; double-check contract.
    assert all(n["as_of_ms"] <= 50 for n in pit["nodes"])


def test_break_overwrite_lineage_forbidden() -> None:
    g = DecisionMemoryGraph()
    n = g.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "BTCUSDT", "label": "BTCUSDT"})
    with pytest.raises(DecisionMemoryGraphError, match="lineage_rewrite_forbidden"):
        g.rewrite_lineage(n["node_id"], "0" * 64)


def test_break_storage_update_delete_banned() -> None:
    store = InMemoryGraphStorage()
    with pytest.raises(Exception, match="mutation_forbidden|deletion_forbidden"):
        store.update_node("x", {})
    with pytest.raises(Exception, match="deletion_forbidden"):
        store.delete_node("x")
    with pytest.raises(Exception, match="mutation_forbidden"):
        store.update_edge("e", {})


def test_break_private_leak_detector() -> None:
    with pytest.raises(HardBanViolation, match="no_private_field_leak"):
        assert_no_private_leak({"payload": {"api_secret": "x"}})
    with pytest.raises(HardBanViolation, match="no_private_field_leak"):
        assert_no_private_leak({"raw_memory_graph": True})


def test_break_unavailable_does_not_invent_nodes() -> None:
    resp = unavailable_response(operation="pit_lookup")
    assert resp["nodes"] == []
    assert resp["edges"] == []
    assert resp["results"] == []
    assert is_fail_safe(resp)


def test_break_public_safe_keys_are_whitelist() -> None:
    assert "api_key" not in PUBLIC_SAFE_PAYLOAD_KEYS
    assert "proprietary_threshold" not in PUBLIC_SAFE_PAYLOAD_KEYS
    assert "founder_only_note" not in PUBLIC_SAFE_PAYLOAD_KEYS
    assert PRIVATE_FIELD_NAMES.isdisjoint(PUBLIC_SAFE_PAYLOAD_KEYS)


def test_break_similarity_without_pit_rejected() -> None:
    q = build_similarity_query(
        query_id="np",
        as_of_ms=1,
        anchor_node_id="a",
        dimensions={},
    )
    q["pit_bound"] = False
    with pytest.raises(SimilarityQueryError, match="must_be_pit_bound"):
        validate_similarity_query(q)


def test_break_seal_secret_in_edge_attrs() -> None:
    g = DecisionMemoryGraph()
    a = g.seal_node(kind="SYMBOL", as_of_ms=1, payload={"symbol": "BTCUSDT", "label": "BTCUSDT"})
    b = g.seal_node(kind="MARKET_SNAPSHOT", as_of_ms=1, payload={"symbol": "BTCUSDT", "summary": "s"})
    with pytest.raises(HardBanViolation, match="no_secret_storage"):
        g.seal_edge(
            kind="OF_SYMBOL",
            from_id=b["node_id"],
            to_id=a["node_id"],
            as_of_ms=1,
            attrs={"token": "leakleakleakleakleak"},
        )


def test_break_nested_secret_key_rejected() -> None:
    g = DecisionMemoryGraph()
    with pytest.raises(HardBanViolation, match="no_secret_storage"):
        g.seal_node(
            kind="CRITIC",
            as_of_ms=1,
            payload={"summary": "x", "meta": {"authorization": "NESTED_REDACTED_CREDENTIAL_001"}},
        )


def test_break_public_node_when_unavailable() -> None:
    store = InMemoryGraphStorage()
    g = DecisionMemoryGraph(storage=store)
    store.mark_unavailable()
    pub = g.public_node("any")
    assert pub is not None
    assert pub.get("unavailable") is True
    assert pub.get("raw_memory_graph") is False
    assert pub.get("payload") == {}
    assert_no_private_leak(pub)


def test_break_pit_ordering_deterministic() -> None:
    g = DecisionMemoryGraph()
    for i, sym in enumerate(("ZZUSDT", "AAUSDT", "MMUSDT")):
        g.seal_node(
            kind="SYMBOL",
            as_of_ms=10,
            payload={"symbol": sym, "label": sym},
            node_id=f"dmg_sym_{sym}",
        )
    a = g.pit_lookup(as_of_ms=10)
    b = g.pit_lookup(as_of_ms=10)
    assert [n["node_id"] for n in a["nodes"]] == [n["node_id"] for n in b["nodes"]]
