class FleetCapitalAllocator:
    def __init__(self, ledger):
        self.ledger = ledger

    def allocate_from_reserve(self, fleet, amount, reason):
        self.ledger.transfer_from_reserve(fleet, amount, reason)
        return self.ledger.snapshot()["fleets"][fleet]

