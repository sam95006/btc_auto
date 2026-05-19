from base_strategy_engine import BaseFleetStrategyEngine


class FleetBtcStrategyEngine(BaseFleetStrategyEngine):
    def __init__(self, *args):
        super().__init__("BTC", *args)

