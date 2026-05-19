from datetime import datetime
from threading import RLock


class SystemStateManager:
    def __init__(self):
        self._lock = RLock()
        self.state = {
            "running": True,
            "alert_level": "NORMAL",
            "emergency_meeting": False,
            "trading_paused": False,
            "system_health": "ONLINE",
            "current_time": "",
            "module_health": {},
            "fleet_status": {
                fleet: {
                    "status": "STANDBY",
                    "last_signal": "HOLD",
                    "last_reason": "Waiting for market data",
                }
                for fleet in ["BTC", "ETH", "SOL", "PEPE"]
            },
        }

    def snapshot(self):
        with self._lock:
            self.state["current_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return {
                **self.state,
                "module_health": dict(self.state["module_health"]),
                "fleet_status": {
                    fleet: dict(item)
                    for fleet, item in self.state["fleet_status"].items()
                },
            }

    def set_module_health(self, module, status):
        with self._lock:
            self.state["module_health"][module] = status

    def update_fleet(self, fleet, **updates):
        with self._lock:
            self.state["fleet_status"].setdefault(
                fleet,
                {"status": "STANDBY", "last_signal": "HOLD", "last_reason": "Initialized"},
            )
            self.state["fleet_status"][fleet].update(updates)

    def set_alert(self, level, emergency=False, trading_paused=False):
        with self._lock:
            self.state["alert_level"] = level
            self.state["emergency_meeting"] = emergency
            self.state["trading_paused"] = trading_paused

    def clear_alert(self):
        self.set_alert("NORMAL", emergency=False, trading_paused=False)
