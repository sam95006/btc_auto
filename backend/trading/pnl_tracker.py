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
            unrealized_by_fleet[pos["fleet"]] += pos.get("unrealized_pnl", 0.0)

        fleets = {}
        for fleet in realized_by_fleet:
            fleets[fleet] = {
                "realized": round(realized_by_fleet[fleet], 4),
                "unrealized": round(unrealized_by_fleet[fleet], 4),
                "total": round(realized_by_fleet[fleet] + unrealized_by_fleet[fleet], 4),
            }

        total_realized = sum(item["realized"] for item in fleets.values())
        total_unrealized = sum(item["unrealized"] for item in fleets.values())
        return {
            "fleets": fleets,
            "total_realized": round(total_realized, 4),
            "total_unrealized": round(total_unrealized, 4),
            "total_pnl": round(total_realized + total_unrealized, 4),
        }

