from base_strategy_engine import BaseFleetStrategyEngine


class FleetEthStrategyEngine(BaseFleetStrategyEngine):
    def __init__(self, *args):
        super().__init__("ETH", *args)

