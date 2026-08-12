"""V14-J Experiment Registry tests — fail-closed immutability and cherry-pick bans."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_experiment_registry import (
    HARD_BAN_FLAGS,
    IDENTITY_FIELDS,
    ExperimentRecordError,
    ExperimentRegistryError,
    ImmutableExperimentRegistry,
    build_experiment_record,
    checksum_parameters,
    checksum_universe,
    resolve_version_pins,
    verify_experiment_record,
)
from backend.nexus_experiment_registry.hashing import sha256_hex


REPO = Path(__file__).resolve().parents[2]


def _rh(tag: str) -> str:
    return sha256_hex({"t": tag})


def _kw(**over: object) -> dict:
    pins = resolve_version_pins(REPO)
    base = {
        "experiment_id": "t1",
        "mechanism_semantic_id": "mech_t",
        "data_lineage": {
            "source_ids": ["src_a"],
            "as_of_ms": 1_700_000_000_000,
            "pit_bound": True,
        },
        "universe_checksum": checksum_universe(["BTCUSDT"], as_of_ms=1_700_000_000_000),
        "feature_version": pins["feature_version"],
        "code_checksum": pins["code_checksum"],
        "parameter_checksum": checksum_parameters({"a": 1}),
        "cost_version": pins["cost_version"],
        "risk_version": pins["risk_version"],
        "execution_version": pins["execution_version"],
        "time_intervals": [
            {
                "interval_id": "d1",
                "label": "dev",
                "start_ms": 1,
                "end_ms": 2,
                "category": "development",
            }
        ],
        "development_only": True,
        "oos_consumed": False,
        "seeds": {"primary": 1},
        "result_hashes": {"primary": _rh("r1")},
    }
    base.update(over)
    return base  # type: ignore[return-value]


def test_version_pins_bound() -> None:
    pins = resolve_version_pins(REPO)
    assert pins["cost_version"]
    assert pins["risk_version"]
    assert pins["execution_version"]
    assert pins["feature_version"]
    assert pins["code_checksum"]
    assert len(pins["risk_gates_fingerprint"]) == 64


def test_build_and_verify_record() -> None:
    rec = build_experiment_record(**_kw())
    assert rec["schema"]
    assert rec["identity_fingerprint"]
    assert rec["record_hash"]
    assert rec["oos_consumed"] is False
    for k, v in HARD_BAN_FLAGS.items():
        assert rec[k] is v
    out = verify_experiment_record(rec)
    assert out["ok"] is True


def test_identity_fields_exclude_results() -> None:
    assert "result_hashes" not in IDENTITY_FIELDS
    assert "experiment_id" not in IDENTITY_FIELDS


def test_oos_consumed_forbidden() -> None:
    with pytest.raises(ExperimentRecordError, match="oos_consumed_forbidden"):
        build_experiment_record(**_kw(oos_consumed=True))


def test_register_and_duplicate_id() -> None:
    reg = ImmutableExperimentRegistry()
    rec = build_experiment_record(**_kw())
    reg.register(rec)
    with pytest.raises(ExperimentRegistryError, match="experiment_id_duplicate"):
        reg.register(rec)


def test_exact_duplicate_identity() -> None:
    reg = ImmutableExperimentRegistry()
    reg.register(build_experiment_record(**_kw(experiment_id="a")))
    with pytest.raises(ExperimentRegistryError, match="exact_duplicate_identity"):
        reg.register(build_experiment_record(**_kw(experiment_id="b")))


def test_divergent_result_conflict() -> None:
    reg = ImmutableExperimentRegistry()
    reg.register(build_experiment_record(**_kw(experiment_id="a", result_hashes={"primary": _rh("x")})))
    with pytest.raises(ExperimentRegistryError, match="identity_result_conflict"):
        reg.register(
            build_experiment_record(
                **_kw(experiment_id="b", result_hashes={"primary": _rh("favorable")})
            )
        )


def test_parent_lineage() -> None:
    reg = ImmutableExperimentRegistry()
    reg.register(build_experiment_record(**_kw(experiment_id="p", mechanism_semantic_id="m_p")))
    reg.register(
        build_experiment_record(
            **_kw(
                experiment_id="c",
                mechanism_semantic_id="m_c",
                parent_experiment="p",
                seeds={"primary": 2},
                parameter_checksum=checksum_parameters({"a": 2}),
                result_hashes={"primary": _rh("c")},
            )
        )
    )
    assert reg.lineage_chain("c") == ["c", "p"]


def test_parent_missing() -> None:
    reg = ImmutableExperimentRegistry()
    with pytest.raises(ExperimentRegistryError, match="parent_experiment_missing"):
        reg.register(
            build_experiment_record(**_kw(parent_experiment="nope"))
        )


def test_self_parent_blocked() -> None:
    reg = ImmutableExperimentRegistry()
    with pytest.raises(ExperimentRegistryError, match="parent_experiment_self_reference"):
        reg.register(
            build_experiment_record(**_kw(experiment_id="x", parent_experiment="x"))
        )


def test_immutability() -> None:
    reg = ImmutableExperimentRegistry()
    reg.register(build_experiment_record(**_kw()))
    with pytest.raises(ExperimentRegistryError, match="mutation_forbidden"):
        reg.update("t1")
    with pytest.raises(ExperimentRegistryError, match="deletion_forbidden"):
        reg.delete("t1")


def test_silent_cherry_pick_omission() -> None:
    reg = ImmutableExperimentRegistry()
    for i, eid in enumerate(["a", "b", "c"]):
        reg.register(
            build_experiment_record(
                **_kw(
                    experiment_id=eid,
                    seeds={"primary": i + 10},
                    parameter_checksum=checksum_parameters({"a": i + 10}),
                    result_hashes={"primary": _rh(eid)},
                )
            )
        )
    reg.declare_candidacy_set(
        candidacy_id="s1",
        member_experiment_ids=["a", "b", "c"],
        selection_criterion="disclosed_full_set",
    )
    with pytest.raises(ExperimentRegistryError, match="silent_cherry_pick_omission"):
        reg.select_from_candidacy(
            candidacy_id="s1",
            selected_experiment_id="c",
            disclose_all_member_ids=["c"],
        )
    sel = reg.select_from_candidacy(
        candidacy_id="s1",
        selected_experiment_id="c",
        disclose_all_member_ids=["a", "b", "c"],
    )
    assert sel["silent_cherry_picking"] is False


def test_favorable_criterion_banned() -> None:
    reg = ImmutableExperimentRegistry()
    for i, eid in enumerate(["a", "b"]):
        reg.register(
            build_experiment_record(
                **_kw(
                    experiment_id=eid,
                    seeds={"primary": i + 20},
                    parameter_checksum=checksum_parameters({"a": i + 20}),
                    result_hashes={"primary": _rh(f"f{eid}")},
                )
            )
        )
    with pytest.raises(ExperimentRegistryError, match="silent_favorable_criterion_banned"):
        reg.declare_candidacy_set(
            candidacy_id="bad",
            member_experiment_ids=["a", "b"],
            selection_criterion="best",
        )


def test_attempt_silent_cherry_pick_always_banned() -> None:
    reg = ImmutableExperimentRegistry()
    with pytest.raises(ExperimentRegistryError, match="silent_cherry_picking_banned"):
        reg.attempt_silent_cherry_pick(
            favorable_experiment_id="win",
            omitted_experiment_ids=["lose1"],
        )


def test_persist_reload(tmp_path: Path) -> None:
    reg = ImmutableExperimentRegistry(tmp_path)
    reg.register(build_experiment_record(**_kw(experiment_id="p1", mechanism_semantic_id="m1")))
    path = tmp_path / "registry.json"
    reg.save(path)
    loaded = ImmutableExperimentRegistry.load(path)
    assert len(loaded) == 1
    assert loaded.verify_all()["ok"] is True


def test_registry_hash_tamper(tmp_path: Path) -> None:
    reg = ImmutableExperimentRegistry(tmp_path)
    reg.register(build_experiment_record(**_kw(experiment_id="p1", mechanism_semantic_id="m1")))
    path = tmp_path / "registry.json"
    snap = reg.snapshot()
    snap["registry_hash"] = "ab" * 32
    path.write_text(__import__("json").dumps(snap), encoding="utf-8")
    with pytest.raises(ExperimentRegistryError, match="registry_hash_mismatch"):
        ImmutableExperimentRegistry.load(path)


def test_hard_ban_flip_fail_closed() -> None:
    rec = build_experiment_record(**_kw())
    rec["exchange_write"] = True
    with pytest.raises(ExperimentRecordError, match="hard_ban_violated:exchange_write"):
        verify_experiment_record(rec)
