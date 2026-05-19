from datetime import datetime
from threading import RLock

from backend.wallet.mock_wallet_service import MockWalletService


class InternalCapitalLedger:
    def __init__(self, wallet=None):
        self._lock = RLock()
        balances = (wallet or MockWalletService()).initial_balances()
        self.hq_reserve = balances["hq_reserve"]
        self.radar_budget = balances["radar_budget"]
        self.radar_frozen = 0.0
        self.fleets = {
            fleet: {
                "allocated": amount,
                "available": amount,
                "frozen": 0.0,
                "realized_pnl": 0.0,
            }
            for fleet, amount in balances["fleets"].items()
        }
        self.ledger_entries = []

    def record(self, entry_type, fleet, amount, note):
        self.ledger_entries.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": entry_type,
            "fleet": fleet,
            "amount": round(amount, 6),
            "note": note,
        })
        self.ledger_entries = self.ledger_entries[:300]

    def freeze(self, fleet, amount, note="paper order margin"):
        with self._lock:
            account = self.fleets[fleet]
            if account["available"] + 1e-9 < amount:
                raise ValueError(f"{fleet} available capital insufficient")
            account["available"] -= amount
            account["frozen"] += amount
            self.record("FREEZE", fleet, amount, note)

    def release(self, fleet, margin, pnl=0.0, note="paper position closed"):
        with self._lock:
            account = self.fleets[fleet]
            account["frozen"] = max(0.0, account["frozen"] - margin)
            account["available"] += margin + pnl
            account["realized_pnl"] += pnl
            self.record("RELEASE", fleet, margin + pnl, note)

    def freeze_radar(self, amount, note="radar order margin"):
        with self._lock:
            amount = round(float(amount or 0.0), 6)
            if self.radar_budget + 1e-9 < amount:
                raise ValueError("RADAR budget insufficient")
            self.radar_budget -= amount
            self.radar_frozen += amount
            self.record("RADAR_FREEZE", "RADAR", amount, note)

    def release_radar(self, margin, pnl=0.0, note="radar position closed"):
        with self._lock:
            margin = round(float(margin or 0.0), 6)
            pnl = round(float(pnl or 0.0), 6)
            self.radar_frozen = max(0.0, self.radar_frozen - margin)
            self.radar_budget += margin + pnl
            self.record("RADAR_RELEASE", "RADAR", margin + pnl, note)

    def radar_available(self):
        with self._lock:
            return round(float(self.radar_budget or 0.0), 6)

    def transfer_from_reserve(self, fleet, amount, note="HQ reserve allocation"):
        with self._lock:
            if self.hq_reserve + 1e-9 < amount:
                raise ValueError("HQ reserve insufficient")
            self.hq_reserve -= amount
            self.fleets[fleet]["allocated"] += amount
            self.fleets[fleet]["available"] += amount
            self.record("RESERVE_TRANSFER", fleet, amount, note)

    def apply_live_distribution(self, hq_reserve, radar_budget, fleet_allocations):
        with self._lock:
            self.hq_reserve = round(float(hq_reserve or 0.0), 6)
            self.radar_budget = round(float(radar_budget or 0.0), 6)
            self.radar_frozen = round(min(float(self.radar_frozen or 0.0), self.radar_budget + float(self.radar_frozen or 0.0)), 6)
            for fleet, target_allocated in fleet_allocations.items():
                account = self.fleets.setdefault(
                    fleet,
                    {
                        "allocated": 0.0,
                        "available": 0.0,
                        "frozen": 0.0,
                        "realized_pnl": 0.0,
                    },
                )
                target_allocated = round(float(target_allocated or 0.0), 6)
                frozen = float(account.get("frozen", 0.0) or 0.0)
                realized = float(account.get("realized_pnl", 0.0) or 0.0)
                account["allocated"] = target_allocated
                account["available"] = round(max(target_allocated - frozen, 0.0), 6)
                account["frozen"] = round(min(frozen, target_allocated), 6)
                account["realized_pnl"] = realized

    def sync_live_futures_margins(self, margin_by_fleet):
        with self._lock:
            for fleet, account in self.fleets.items():
                allocated = float(account.get("allocated", 0.0) or 0.0)
                live_margin = round(float(margin_by_fleet.get(fleet, 0.0) or 0.0), 6)
                live_margin = min(max(live_margin, 0.0), allocated)
                account["frozen"] = live_margin
                account["available"] = round(max(allocated - live_margin, 0.0), 6)

    def snapshot(self):
        with self._lock:
            active_total = sum(v["available"] + v["frozen"] for v in self.fleets.values())
            realized = sum(v["realized_pnl"] for v in self.fleets.values())
            return {
                "total": round(self.hq_reserve + self.radar_budget + active_total, 4),
                "hq_reserve": round(self.hq_reserve, 4),
                "radar_budget": round(self.radar_budget, 4),
                "radar_frozen": round(self.radar_frozen, 4),
                "radar_available": round(self.radar_budget, 4),
                "active_total": round(active_total, 4),
                "realized_pnl": round(realized, 4),
                "fleets": {k: dict(v) for k, v in self.fleets.items()},
                "entries": list(self.ledger_entries[:80]),
            }

