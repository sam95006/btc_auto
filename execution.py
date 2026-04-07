class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0
        self.entry_price = 0
        self.cumulative_pnl = initial_cumulative_pnl
        self.trailing_high = 0
        self.trailing_low = 0
        self.max_daily_drawdown = -350

    def execute(self, signal, current_price, storage=None, ml_prob=0.5, atr=0):
        report = ""
        if self.cumulative_pnl < self.max_daily_drawdown:
            return "🆘 [斷路器已啟動] 今日虧損過高，系統暫時停止開倉。"

        atr_sl_pct = max(0.015, (atr * 2.5) / current_price) if atr > 0 else 0.015
        
        # 1. 檢查止盈止損 (不論是 BUY 還是 SUPER_BUY)
        if self.position > 0:
            self.trailing_high = max(self.trailing_high, current_price)
            if storage: storage.update_active_pos("BTC", "LONG", self.entry_price, self.position, self.trailing_high)
            
            # 動態止損/追蹤止盈
            if current_price < self.entry_price * (1 - atr_sl_pct) or \
               current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade("TSL_LONG_EXIT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos("BTC", "NONE", 0, 0)
                report = f"✅ 【多單平倉】 出場: ${current_price:,.2f} | 盈虧: ${pnl:,.2f} | 累積: ${self.cumulative_pnl:,.2f}"
                self.position = 0

        # ... (Short 部分省略，邏輯一致)

        # 2. 開倉判定 (增加 SUPER_BUY 專用倉位)
        if self.position == 0:
            # 💡 [SUPER BUY] 偵測到全市場最強共振：下重注 (25%)
            if signal == "SUPER_BUY":
                qty = (self.cash * 0.25) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                if storage: storage.update_active_pos("BTC", "LONG", current_price, qty, current_price)
                report = f"🌋 【!!超級多單出擊!!】 全方位共振訊號！開倉點: ${current_price:,.2f} | 倉位: 25% 重倉"

            elif signal == "BUY" and ml_prob > 0.75:
                qty = (self.cash * 0.1) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                if storage: storage.update_active_pos("BTC", "LONG", current_price, qty, current_price)
                report = f"🔥 【標準多單入手中】 開倉點: ${current_price:,.2f} | 倉位: 10% 試探"

            elif signal == "SELL" and ml_prob < 0.25:
                qty = (self.cash * 0.1) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                if storage: storage.update_active_pos("BTC", "SHORT", current_price, qty, current_price)
                report = f"❄️ 【標準空單入手中】 開倉點: ${current_price:,.2f} | 倉位: 10% 試探"

        return report
