class BinancePositionSyncService:
    def __init__(self, futures_client=None):
        self.futures_client = futures_client

    def sync_positions(self):
        if not (self.futures_client and self.futures_client.is_configured()):
            return []
        return self.futures_client.get_all_position_risk()

    def sync_funding_rates(self, symbols):
        items = []
        if not (self.futures_client and self.futures_client.is_configured()):
            return items
        for symbol in symbols:
            try:
                items.extend(self.futures_client.get_funding_rate_history(symbol=symbol, limit=10))
            except Exception:
                pass
        return items
