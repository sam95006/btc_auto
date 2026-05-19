class BinanceOrderSyncService:
    def __init__(self, spot_client=None, futures_client=None):
        self.spot_client = spot_client
        self.futures_client = futures_client

    def sync_spot_orders_and_trades(self, symbols):
        open_orders = []
        trade_history = []
        if not (self.spot_client and self.spot_client.is_configured()):
            return open_orders, trade_history
        for symbol in symbols:
            try:
                open_orders.extend(self.spot_client.get_open_orders(symbol=symbol))
            except Exception:
                continue
            try:
                trade_history.extend(self.spot_client.get_my_trades(symbol=symbol, limit=50))
            except Exception:
                continue
        return open_orders, trade_history

    def sync_futures_orders_and_fills(self, symbol_map):
        open_orders = []
        fills = []
        if not (self.futures_client and self.futures_client.is_configured()):
            return open_orders, fills
        for symbol in symbol_map:
            try:
                open_orders.extend(self.futures_client.get_open_orders(symbol=symbol))
            except Exception:
                pass
            try:
                fills.extend(self.futures_client.get_user_trades(symbol=symbol, limit=50))
            except Exception:
                pass
        return open_orders, fills
