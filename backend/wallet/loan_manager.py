from datetime import datetime
from threading import RLock

from backend.config.capital_config import LOAN_INTEREST_DAILY, LOAN_MAX, LOAN_UNIT


class LoanManager:
    def __init__(self, ledger):
        self.ledger = ledger
        self._lock = RLock()
        self.loans = {fleet: [] for fleet in ["BTC", "ETH", "SOL", "PEPE"]}

    def borrow(self, fleet):
        with self._lock:
            current = sum(item["principal"] for item in self.loans[fleet])
            if current + LOAN_UNIT > LOAN_MAX:
                raise ValueError(f"{fleet} loan limit exceeded")
            self.ledger.transfer_from_reserve(fleet, LOAN_UNIT, "internal paper loan")
            loan = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "principal": LOAN_UNIT,
                "interest_daily": LOAN_INTEREST_DAILY,
            }
            self.loans[fleet].append(loan)
            return loan

    def repay_from_available(self, fleet):
        with self._lock:
            if not self.loans[fleet]:
                return 0.0
            account = self.ledger.fleets[fleet]
            repaid = 0.0
            while self.loans[fleet] and account["available"] > 0:
                loan = self.loans[fleet][0]
                due = loan["principal"] * (1.0 + loan["interest_daily"])
                amount = min(account["available"], due)
                account["available"] -= amount
                self.ledger.hq_reserve += amount
                repaid += amount
                if amount + 1e-9 >= due:
                    self.loans[fleet].pop(0)
                else:
                    loan["principal"] -= amount
                    break
            if repaid:
                self.ledger.record("LOAN_REPAY", fleet, repaid, "priority internal repayment")
            return repaid

    def snapshot(self):
        with self._lock:
            return {
                fleet: {
                    "principal": round(sum(item["principal"] for item in loans), 4),
                    "count": len(loans),
                    "limit": LOAN_MAX,
                }
                for fleet, loans in self.loans.items()
            }

