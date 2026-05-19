from nexus.config.capital_config import RISK_LIMITS


class RiskControlEngine:
    def __init__(self, ledger, pnl_tracker):
        self.ledger = ledger
        self.pnl_tracker = pnl_tracker

    def validate_order(self, order, meeting_notes=None):
        fleet = order["fleet"]
        leverage = order.get("leverage", 1.0)
        margin = order.get("margin", 0.0)
        meeting_notes = meeting_notes or {}
        forbidden_text = " ".join(meeting_notes.get("forbidden_actions", []))
        if fleet in forbidden_text and "ç¦æ­¢" in forbidden_text:
            return False, "?ƒè­°ç¦ä»¤?åˆ¶æ­¤è‰¦?Šæ?ä½?
        if leverage > RISK_LIMITS["max_leverage"]:
            return False, "æ§“æ¡¿è¶…é?æ¨¡æ“¬é¢¨æ§ä¸Šé?"

        account = self.ledger.snapshot()["fleets"][fleet]
        if margin > account["available"]:
            return False, "?¯ç”¨æ¨¡æ“¬è³‡é?ä¸è¶³"

        notional = margin * leverage
        max_notional = account["allocated"] * RISK_LIMITS["max_position_notional_pct"]
        if notional > max_notional:
            return False, "?¨ä??ç›®?¹å€¼è??è‰¦?Šä???

        fleet_pnl = self.pnl_tracker.snapshot()["fleets"][fleet]["total"]
        if fleet_pnl <= RISK_LIMITS["fleet_max_loss"]:
            return False, "?¦é??§æ??”é¢¨?§é???
        return True, "?šé?é¢¨æ§"

    def should_trigger_emergency(self):
        pnl = self.pnl_tracker.snapshot()
        if pnl["total_pnl"] <= RISK_LIMITS["system_daily_max_loss"]:
            return True, "ç³»çµ±?®æ—¥?§æ?è¶…é??åˆ¶"
        for fleet, item in pnl["fleets"].items():
            if item["total"] <= RISK_LIMITS["fleet_max_loss"]:
                return True, f"{fleet} ?¦é??§æ?è¶…é??åˆ¶"
        return False, ""
