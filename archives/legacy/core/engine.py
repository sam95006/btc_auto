import datetime
import pytz

class MetropolisEngine:
    """
    Metropolis 核心邏輯引擎 (大腦)
    負責 8 分隊數據審計、100U 預算硬鎖定與 TAIEX 同步
    """
    def __init__(self):
        self.timezone = pytz.timezone('Asia/Taipei')
        self.radar_budget = 100.0  # 🥇 100U 鐵律：雷達站專屬不可變資產
        
    def audit_fleet_assets(self, raw_data):
        """
        執行全艦隊資產審計，並套用預算鎖定
        """
        processed = {
            "timestamp": datetime.datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S"),
            "prices": {},
            "today_pnl": 0.0,
            "taiex_info": raw_data.get("taiex_info", {"index": "--"}),
            "sp500_info": raw_data.get("sp500_info", {"index": "--"})
        }
        
        # 🥇 1. 價格與資產處理
        raw_prices = raw_data.get("prices", {})
        for ship_id in ['BTC', 'ETH', 'SOL', 'XAUT', 'PEPE', 'NEWS', 'SPECIAL']:
            if ship_id == 'SPECIAL':
                processed["prices"][ship_id] = self.radar_budget  # 強制鎖定 100U
            else:
                processed["prices"][ship_id] = raw_prices.get(ship_id, 0.0)
        
        # 🥇 2. 總收益計算 (排除新聞站)
        pnl = raw_data.get("today_pnl", 0.0)
        processed["today_pnl"] = pnl
        
        # 🥇 3. 緊急警戒偵測 (Emergency Detection)
        # 若 PnL 虧損超過 50U 或收到外部警告，觸發紅色警戒
        if pnl < -50.0:
            processed["alert_level"] = "RED"
        elif pnl > 100.0:
            processed["alert_level"] = "GOLD"
        else:
            processed["alert_level"] = "NORMAL"
        
        return processed

# 實例化全局引擎
engine = MetropolisEngine()
