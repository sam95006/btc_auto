"""Immutable append-only experiment registry with cherry-pick guards."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_experiment_registry.constants import (
    HARD_BAN_FLAGS,
    REGISTRY_SCHEMA,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_experiment_registry.hashing import canonical_dumps, sha256_hex
from backend.nexus_experiment_registry.record import (
    ExperimentRecordError,
    build_experiment_record,
    verify_experiment_record,
)


class ExperimentRegistryError(ValueError):
    """Fail-closed registry error (duplicates, cherry-picks, lineage breaks)."""


class ImmutableExperimentRegistry:
    """Append-only sealed registry.

    Prevents silent favorable-run cherry-picking by:
      * rejecting identity collisions with divergent result hashes
      * rejecting exact duplicate re-registration
      * requiring every candidacy-set member to be registered before selection
      * forbidding mutation / deletion of sealed records
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else None
        self._by_id: dict[str, dict[str, Any]] = {}
        self._by_identity: dict[str, str] = {}  # fingerprint -> experiment_id
        self._order: list[str] = []
        self._candidacy: dict[str, dict[str, Any]] = {}
        self._selections: dict[str, dict[str, Any]] = {}

    # --- introspection -------------------------------------------------

    def __len__(self) -> int:
        return len(self._order)

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        rec = self._by_id.get(experiment_id)
        return dict(rec) if rec else None

    def list_ids(self) -> list[str]:
        return list(self._order)

    def records(self) -> list[dict[str, Any]]:
        return [dict(self._by_id[i]) for i in self._order]

    # --- immutability bans ---------------------------------------------

    def update(self, *_args: Any, **_kwargs: Any) -> None:
        raise ExperimentRegistryError("mutation_forbidden_immutable_registry")

    def delete(self, *_args: Any, **_kwargs: Any) -> None:
        raise ExperimentRegistryError("deletion_forbidden_immutable_registry")

    def overwrite(self, *_args: Any, **_kwargs: Any) -> None:
        raise ExperimentRegistryError("overwrite_forbidden_immutable_registry")

    # --- registration --------------------------------------------------

    def register(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append a sealed record. Fail-closed on duplicates / cherry-picks."""
        verify_experiment_record(record)
        eid = record["experiment_id"]
        if eid in self._by_id:
            raise ExperimentRegistryError(f"experiment_id_duplicate:{eid}")

        fp = record["identity_fingerprint"]
        existing_id = self._by_identity.get(fp)
        if existing_id is not None:
            existing = self._by_id[existing_id]
            if existing["result_hashes"] == record["result_hashes"]:
                raise ExperimentRegistryError(
                    f"exact_duplicate_identity:{existing_id}"
                )
            # Same setup, different results → nondeterminism or cherry-pick attempt.
            raise ExperimentRegistryError(
                "identity_result_conflict:"
                f"{existing_id}->{eid}:"
                "silent_cherry_pick_or_nondeterminism"
            )

        parent = record.get("parent_experiment")
        if parent is not None:
            if not parent:
                raise ExperimentRegistryError("parent_experiment_empty_string")
            if parent == eid:
                raise ExperimentRegistryError("parent_experiment_self_reference")
            if parent not in self._by_id:
                raise ExperimentRegistryError(f"parent_experiment_missing:{parent}")

        sealed = dict(record)
        self._by_id[eid] = sealed
        self._by_identity[fp] = eid
        self._order.append(eid)
        return {
            "ok": True,
            "experiment_id": eid,
            "identity_fingerprint": fp,
            "record_hash": sealed["record_hash"],
            "index": len(self._order) - 1,
        }

    def register_built(self, **kwargs: Any) -> dict[str, Any]:
        """Build then register a sealed experiment record."""
        record = build_experiment_record(**kwargs)
        return self.register(record)

    # --- candidacy / cherry-pick prevention ----------------------------

    def declare_candidacy_set(
        self,
        *,
        candidacy_id: str,
        member_experiment_ids: list[str],
        selection_criterion: str,
    ) -> dict[str, Any]:
        """Declare a multi-run candidacy set before any favorable selection.

        Every member must already be registered. Selection is deferred until
        ``select_from_candidacy`` is called with an explicit criterion.
        Silent omission of unfavorable members is rejected at selection time.
        """
        cid = str(candidacy_id or "").strip()
        if not cid:
            raise ExperimentRegistryError("candidacy_id_required")
        if cid in self._candidacy:
            raise ExperimentRegistryError(f"candidacy_id_duplicate:{cid}")
        members = [str(m) for m in member_experiment_ids]
        if len(members) < 2:
            raise ExperimentRegistryError("candidacy_requires_at_least_two_members")
        if len(set(members)) != len(members):
            raise ExperimentRegistryError("candidacy_member_ids_not_unique")
        missing = [m for m in members if m not in self._by_id]
        if missing:
            raise ExperimentRegistryError(f"candidacy_members_unregistered:{missing}")
        criterion = str(selection_criterion or "").strip()
        if not criterion:
            raise ExperimentRegistryError("selection_criterion_required")
        if criterion.lower() in {"best", "favorable", "cherry_pick", "max_pnl", "highest"}:
            # Favorable-only criteria without disclosure of losers is banned.
            # Explicit disclosed criteria like "disclosed_max_sharpe_with_full_set" OK.
            if "disclosed" not in criterion.lower() and "full_set" not in criterion.lower():
                raise ExperimentRegistryError(
                    f"silent_favorable_criterion_banned:{criterion}"
                )

        entry = {
            "candidacy_id": cid,
            "member_experiment_ids": members,
            "selection_criterion": criterion,
            "selected_experiment_id": None,
            "selection_disclosed": False,
            "registry_member_hashes": {
                m: self._by_id[m]["record_hash"] for m in members
            },
        }
        self._candidacy[cid] = entry
        return dict(entry)

    def select_from_candidacy(
        self,
        *,
        candidacy_id: str,
        selected_experiment_id: str,
        disclose_all_member_ids: list[str],
    ) -> dict[str, Any]:
        """Select a reported run only with full disclosure of the candidacy set."""
        cid = str(candidacy_id or "").strip()
        if cid not in self._candidacy:
            raise ExperimentRegistryError(f"candidacy_unknown:{cid}")
        entry = self._candidacy[cid]
        if entry["selected_experiment_id"] is not None:
            raise ExperimentRegistryError(f"candidacy_already_selected:{cid}")

        selected = str(selected_experiment_id)
        if selected not in entry["member_experiment_ids"]:
            raise ExperimentRegistryError(
                f"selected_not_in_candidacy:{selected}"
            )

        disclosed = [str(x) for x in disclose_all_member_ids]
        expected = set(entry["member_experiment_ids"])
        provided = set(disclosed)
        if provided != expected:
            omitted = sorted(expected - provided)
            extra = sorted(provided - expected)
            raise ExperimentRegistryError(
                "silent_cherry_pick_omission:"
                f"omitted={omitted}:extra={extra}"
            )

        # Verify seals still match declared candidacy hashes (immutability).
        for mid in entry["member_experiment_ids"]:
            current = self._by_id[mid]["record_hash"]
            if current != entry["registry_member_hashes"][mid]:
                raise ExperimentRegistryError(f"candidacy_member_mutated:{mid}")

        entry["selected_experiment_id"] = selected
        entry["selection_disclosed"] = True
        selection = {
            "candidacy_id": cid,
            "selected_experiment_id": selected,
            "disclosed_member_ids": sorted(disclosed),
            "selection_criterion": entry["selection_criterion"],
            "silent_cherry_picking": False,
            **HARD_BAN_FLAGS,
        }
        self._selections[cid] = selection
        return dict(selection)

    def attempt_silent_cherry_pick(
        self,
        *,
        favorable_experiment_id: str,
        omitted_experiment_ids: list[str],
    ) -> None:
        """Adversarial probe: always raises — silent cherry-pick is banned."""
        raise ExperimentRegistryError(
            "silent_cherry_picking_banned:"
            f"favorable={favorable_experiment_id}:"
            f"omitted={list(omitted_experiment_ids)}"
        )

    # --- lineage -------------------------------------------------------

    def lineage_chain(self, experiment_id: str) -> list[str]:
        """Walk parent links; fail-closed on cycles / breaks."""
        if experiment_id not in self._by_id:
            raise ExperimentRegistryError(f"experiment_unknown:{experiment_id}")
        chain: list[str] = []
        seen: set[str] = set()
        cur: str | None = experiment_id
        while cur is not None:
            if cur in seen:
                raise ExperimentRegistryError(f"lineage_cycle:{cur}")
            if cur not in self._by_id:
                raise ExperimentRegistryError(f"lineage_break:{cur}")
            seen.add(cur)
            chain.append(cur)
            parent = self._by_id[cur].get("parent_experiment")
            cur = parent
        return chain

    def verify_all(self) -> dict[str, Any]:
        """Re-verify every sealed record and identity index integrity."""
        for eid in self._order:
            rec = self._by_id[eid]
            verify_experiment_record(rec)
            fp = rec["identity_fingerprint"]
            if self._by_identity.get(fp) != eid:
                raise ExperimentRegistryError(f"identity_index_corrupt:{eid}")
        return {
            "ok": True,
            "record_count": len(self._order),
            "candidacy_count": len(self._candidacy),
            "selection_count": len(self._selections),
        }

    # --- persistence ---------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        body = {
            "schema": REGISTRY_SCHEMA,
            "program_schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "records": self.records(),
            "order": list(self._order),
            "candidacy_sets": {k: dict(v) for k, v in self._candidacy.items()},
            "selections": {k: dict(v) for k, v in self._selections.items()},
            **HARD_BAN_FLAGS,
            "silent_cherry_picking": False,
            "auto_integration": False,
        }
        body["registry_hash"] = sha256_hex(
            {k: v for k, v in body.items() if k != "registry_hash"}
        )
        return body

    def save(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path else (self.root / "registry.json" if self.root else None)
        if target is None:
            raise ExperimentRegistryError("save_path_required")
        target.parent.mkdir(parents=True, exist_ok=True)
        snap = self.snapshot()
        target.write_text(
            json.dumps(snap, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: Path | str) -> "ImmutableExperimentRegistry":
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        if raw.get("schema") != REGISTRY_SCHEMA:
            raise ExperimentRegistryError(f"registry_schema_mismatch:{raw.get('schema')}")
        expected = sha256_hex({k: v for k, v in raw.items() if k != "registry_hash"})
        if raw.get("registry_hash") != expected:
            raise ExperimentRegistryError("registry_hash_mismatch")
        reg = cls(root=p.parent)
        for rec in raw.get("records") or []:
            # Bypass conflict checks only for trusted sealed reload — re-verify seals.
            verify_experiment_record(rec)
            eid = rec["experiment_id"]
            fp = rec["identity_fingerprint"]
            if eid in reg._by_id:
                raise ExperimentRegistryError(f"load_duplicate_id:{eid}")
            if fp in reg._by_identity:
                raise ExperimentRegistryError(f"load_duplicate_identity:{fp}")
            reg._by_id[eid] = dict(rec)
            reg._by_identity[fp] = eid
            reg._order.append(eid)
        for cid, entry in (raw.get("candidacy_sets") or {}).items():
            reg._candidacy[cid] = dict(entry)
        for cid, sel in (raw.get("selections") or {}).items():
            reg._selections[cid] = dict(sel)
        # Prefer persisted order if present.
        order = raw.get("order")
        if order and list(order) != reg._order:
            # Rebuild order from sealed snapshot when consistent with records.
            if set(order) != set(reg._order):
                raise ExperimentRegistryError("load_order_mismatch")
            reg._order = list(order)
        return reg


def registry_canonical_bytes(snapshot: dict[str, Any]) -> bytes:
    return canonical_dumps(
        {k: v for k, v in snapshot.items() if k != "registry_hash"}
    ).encode("utf-8")
