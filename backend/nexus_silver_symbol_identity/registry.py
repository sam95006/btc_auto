"""In-memory silver instrument registry — fixture / offline use only."""
from __future__ import annotations

from typing import Any

from backend.nexus_silver_symbol_identity.depeg import assert_depeg_periods_retained
from backend.nexus_silver_symbol_identity.lineage import apply_symbol_rename, detect_silent_rename
from backend.nexus_silver_symbol_identity.normalize import normalize_raw_instrument
from backend.nexus_silver_symbol_identity.schema import validate_silver_instrument


class SilverInstrumentRegistry:
    """Canonical silver store with no-erase delisting and rename lineage."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, Any]] = {}
        self._lineages: dict[str, dict[str, Any]] = {}

    def upsert_raw(self, raw: dict[str, Any]) -> dict[str, Any]:
        record = normalize_raw_instrument(raw)
        return self.upsert(record)

    def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
        check = validate_silver_instrument(record)
        if not check["ok"]:
            raise ValueError(f"invalid_silver_record:{check}")
        iid = record["canonical_instrument_id"]
        prior = self._by_id.get(iid)
        if prior is not None:
            # Merge depeg periods — never drop history.
            merged = dict(record)
            before_periods = list(prior.get("depeg_periods") or [])
            after_periods = list(merged.get("depeg_periods") or [])
            keys = {(p.get("asset"), p.get("start_time"), p.get("end_time")) for p in after_periods}
            for p in before_periods:
                key = (p.get("asset"), p.get("start_time"), p.get("end_time"))
                if key not in keys:
                    after_periods.append(p)
            merged["depeg_periods"] = after_periods
            retention = assert_depeg_periods_retained(prior, merged)
            if not retention["ok"]:
                raise ValueError(f"depeg_retention_failed:{retention}")
            # Delisting is sticky: once delisted, do not erase the stamp.
            if prior.get("delisting_time") and not merged.get("delisting_time"):
                merged["delisting_time"] = prior["delisting_time"]
                merged["status"] = prior.get("status") or "delisted"
            # Rename lineage links are sticky.
            for link in ("rename_lineage_id", "predecessor_instrument_id", "successor_instrument_id"):
                if prior.get(link) and not merged.get(link):
                    merged[link] = prior[link]
            record = merged
        self._by_id[iid] = dict(record)
        return dict(record)

    def get(self, canonical_instrument_id: str) -> dict[str, Any] | None:
        row = self._by_id.get(canonical_instrument_id)
        return dict(row) if row else None

    def list_all(self, *, include_delisted: bool = True) -> list[dict[str, Any]]:
        rows = [dict(v) for v in self._by_id.values()]
        if include_delisted:
            return sorted(rows, key=lambda r: r["canonical_instrument_id"])
        return sorted(
            [r for r in rows if r.get("status") == "active" and not r.get("delisting_time")],
            key=lambda r: r["canonical_instrument_id"],
        )

    def mark_delisted(self, canonical_instrument_id: str, *, delisting_time: str) -> dict[str, Any]:
        row = self._by_id.get(canonical_instrument_id)
        if row is None:
            raise KeyError(canonical_instrument_id)
        updated = dict(row)
        updated["delisting_time"] = delisting_time
        updated["status"] = "delisted"
        self._by_id[canonical_instrument_id] = updated
        # Prove non-erasure: id still present.
        assert canonical_instrument_id in self._by_id
        return dict(updated)

    def erase_forbidden(self, canonical_instrument_id: str) -> dict[str, Any]:
        """Hard ban: delisted instruments must not be erased."""
        if canonical_instrument_id in self._by_id:
            return {
                "ok": False,
                "status": "ERASE_FORBIDDEN",
                "canonical_instrument_id": canonical_instrument_id,
            }
        return {"ok": True, "status": "ABSENT"}

    def rename(
        self,
        *,
        old_instrument_id: str,
        new_symbol: str,
        effective_time: str,
        new_contract_rule_version: str | None = None,
    ) -> dict[str, Any]:
        old = self._by_id.get(old_instrument_id)
        if old is None:
            raise KeyError(old_instrument_id)
        silent = detect_silent_rename(
            previous_symbol=str(old["exchange_symbol"]),
            observed_symbol=new_symbol,
            rename_lineage_id="pending",
        )
        # pending lineage is intentional; apply_symbol_rename creates real id.
        if str(old["exchange_symbol"]).upper() == str(new_symbol).upper():
            raise ValueError("rename_requires_distinct_symbol")
        _ = silent
        payload = apply_symbol_rename(
            old_record=old,
            new_symbol=new_symbol,
            effective_time=effective_time,
            new_contract_rule_version=new_contract_rule_version,
            normalize_fn=normalize_raw_instrument,
        )
        self.upsert(payload["old"])
        self.upsert(payload["new"])
        self._lineages[payload["rename_lineage_id"]] = {
            "rename_lineage_id": payload["rename_lineage_id"],
            "old_instrument_id": payload["old"]["canonical_instrument_id"],
            "new_instrument_id": payload["new"]["canonical_instrument_id"],
            "effective_time": effective_time,
        }
        return payload

    def by_exchange_symbol(self, exchange: str, exchange_symbol: str) -> list[dict[str, Any]]:
        ex = exchange.lower()
        sym = exchange_symbol.upper()
        return [
            dict(r)
            for r in self._by_id.values()
            if r.get("exchange") == ex and r.get("exchange_symbol") == sym
        ]
