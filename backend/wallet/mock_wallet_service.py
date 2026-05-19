from backend.config.capital_config import FLEET_ACTIVE_CAPITAL, HQ_RESERVE, RADAR_BUDGET, TOTAL_CAPITAL


class MockWalletService:
    """Internal paper wallet only. It never connects to an exchange account."""

    def initial_balances(self):
        return {
            "total": TOTAL_CAPITAL,
            "hq_reserve": HQ_RESERVE,
            "radar_budget": RADAR_BUDGET,
            "fleets": dict(FLEET_ACTIVE_CAPITAL),
        }

