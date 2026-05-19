import random
from datetime import datetime


class FundingRateMonitor:
    def scan(self):
        rates = {
            fleet: round(random.uniform(-0.0006, 0.0009), 6)
            for fleet in ["BTC", "ETH", "SOL", "PEPE"]
        }
        severity = "WARNING" if any(abs(v) > 0.00075 for v in rates.values()) else "NORMAL"
        return {
            "time": datetime.now().strftime("%H:%M:%S"),
            "severity": severity,
            "rates": rates,
            "summary": "è³‡é?è²»ç?æ¨¡æ“¬??Ž§?‹è?ä¸?,
        }
