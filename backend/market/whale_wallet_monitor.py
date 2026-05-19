import random
from datetime import datetime


class WhaleWalletMonitor:
    def scan(self):
        severity = random.choice(["NORMAL", "NORMAL", "NORMAL", "WATCH"])
        if random.random() < 0.03:
            severity = "ALERT_RED"
        return {
            "time": datetime.now().strftime("%H:%M:%S"),
            "severity": severity,
            "summary": "å·¨é¯¨?¢å?æ¨¡æ“¬??Ž§?‹è?ä¸?,
            "tracked_wallets": 24,
        }
