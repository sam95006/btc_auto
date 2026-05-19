from dataclasses import dataclass, field


@dataclass
class SpotAccountSnapshot:
    account_type: str = "spot"
    balances: dict = field(default_factory=dict)
    free: dict = field(default_factory=dict)
    locked: dict = field(default_factory=dict)
    total_equity_usdt: float = 0.0
    open_orders: list = field(default_factory=list)
    trade_history: list = field(default_factory=list)
    last_sync_time: int = 0
    sync_status: str = "disconnected"
    sync_error: str = ""

    def to_dict(self):
        return {
            "account_type": self.account_type,
            "balances": self.balances,
            "free": self.free,
            "locked": self.locked,
            "total_equity_usdt": self.total_equity_usdt,
            "open_orders": self.open_orders,
            "trade_history": self.trade_history,
            "last_sync_time": self.last_sync_time,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
        }


@dataclass
class FuturesAccountSnapshot:
    account_type: str = "futures"
    total_wallet_balance: float = 0.0
    available_balance: float = 0.0
    total_unrealized_profit: float = 0.0
    total_margin_balance: float = 0.0
    positions: list = field(default_factory=list)
    open_orders: list = field(default_factory=list)
    order_updates: list = field(default_factory=list)
    fills: list = field(default_factory=list)
    funding_rates: list = field(default_factory=list)
    last_sync_time: int = 0
    sync_status: str = "disconnected"
    sync_error: str = ""

    def to_dict(self):
        return {
            "account_type": self.account_type,
            "total_wallet_balance": self.total_wallet_balance,
            "available_balance": self.available_balance,
            "total_unrealized_profit": self.total_unrealized_profit,
            "total_margin_balance": self.total_margin_balance,
            "positions": self.positions,
            "open_orders": self.open_orders,
            "order_updates": self.order_updates,
            "fills": self.fills,
            "funding_rates": self.funding_rates,
            "last_sync_time": self.last_sync_time,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
        }


@dataclass
class SyncStatus:
    connected: bool = False
    websocket_status: str = "disconnected"
    rest_snapshot_status: str = "idle"
    last_sync_time: int = 0
    errors: list = field(default_factory=list)

    def to_dict(self):
        return {
            "connected": self.connected,
            "websocket_status": self.websocket_status,
            "rest_snapshot_status": self.rest_snapshot_status,
            "last_sync_time": self.last_sync_time,
            "errors": list(self.errors),
        }
