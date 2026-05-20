class PnlTracker:
    def __init__(self, ledger, position_manager):
        self.ledger = ledger
        self.position_manager = position_manager

    def snapshot(self):
        realized_by_fleet = {
            fleet: account["realized_pnl"]
            for fleet, account in self.ledger.snapshot()["fleets"].items()
        }
        unrealized_by_fleet = {fleet: 0.0 for fleet in realized_by_fleet}
        for pos in self.position_manager.all_positions():
            fleet = str(pos.get("fleet") or "").strip().upper()
            if not fleet:
                continue
            unrealized_by_fleet.setdefault(fleet, 0.0)
            unrealized_by_fleet[fleet] += float(pos.get("unrealized_pnl", 0.0) or 0.0)

        all_fleets = sorted(set(realized_by_fleet.keys()) | set(unrealized_by_fleet.keys()))
        fleets = {}
        for fleet in all_fleets:
            fleets[fleet] = {
                "realized": round(float(realized_by_fleet.get(fleet, 0.0) or 0.0), 4),
                "unrealized": round(float(unrealized_by_fleet.get(fleet, 0.0) or 0.0), 4),
                "total": round(
                    float(realized_by_fleet.get(fleet, 0.0) or 0.0) + float(unrealized_by_fleet.get(fleet, 0.0) or 0.0),
                    4,
                ),
            }

        total_realized = sum(item["realized"] for item in fleets.values())
        total_unrealized = sum(item["unrealized"] for item in fleets.values())
        return {
            "fleets": fleets,
            "total_realized": round(total_realized, 4),
            "total_unrealized": round(total_unrealized, 4),
            "total_pnl": round(total_realized + total_unrealized, 4),
        }

