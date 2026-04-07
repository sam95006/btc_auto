class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0          # 負數: 做空 (Short), 正數: 做多 (Long)
        self.entry_price = 0
        self.cumulative_pnl = initial_cumulative_pnl
        self.trailing_high = 0
        self.trailing_low = 0
        # 黑天鵝防護：日最大虧損限制 3.5%
        self.max_daily_drawdown = -350 # (假設本金 10000)

    def execute(self, signal, current_price, storage=None, ml_prob=0.5, atr=0):
        report = ""
        # 斷路器偵測: 如果累積虧損太誇張，鎖死開倉權限
        if self.cumulative_pnl < self.max_daily_drawdown:
            return "🆘 [斷路器已啟動] 今日虧損過高，系統暫時停止所有開倉動作以保護本金。"

        atr_sl_pct = max(0.015, (atr * 2.5) / current_price) if atr > 0 else 0.015
        
        # 1. 檢查是否需要觸發「追蹤止盈」或「止損」
        if self.position > 0: # 多單中
            self.trailing_high = max(self.trailing_high, current_price)
            # 即時同步持倉狀態到數據庫
            if storage: storage.update_active_pos("BTC", "LONG", self.entry_price, self.position, self.trailing_high)
            
            if current_price < self.entry_price * (1 - atr_sl_pct) or \
               current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade("TSL_LONG_EXIT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos("BTC", "NONE", 0, 0) # 清除資料庫
                report = f"✅ 【多單平倉】 出場: ${current_price:,.2f} | 盈虧: ${pnl:,.2f} | 累積: ${self.cumulative_pnl:,.2f}"
                self.position = 0

        elif self.position < 0: # 空單中
            self.trailing_low = min(self.trailing_low, current_price)
            if storage: storage.update_active_pos("BTC", "SHORT", self.entry_price, abs(self.position), self.trailing_low)
            
            if current_price > self.entry_price * (1 + atr_sl_pct) or \
               current_price > self.trailing_low * (1 + atr_sl_pct * 0.5):
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade("TSL_SHORT_EXIT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos("BTC", "NONE", 0, 0)
                report = f"✅ 【空單平倉】 出場: ${current_price:,.2f} | 盈虧: ${pnl:,.2f} | 累積: ${self.cumulative_pnl:,.2f}"
                self.position = 0

        # 2. 開倉判定
        if self.position == 0:
            if signal == "BUY" and ml_prob > 0.75:
                qty = (self.cash * 0.1) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                if storage: storage.update_active_pos("BTC", "LONG", current_price, qty, current_price)
                report = f"🔥 【多單入手中】 開倉點: ${current_price:,.2f} | 量: {qty:.4f}"

            elif signal == "SELL" and ml_prob < 0.25:
                qty = (self.cash * 0.1) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                if storage: storage.update_active_pos("BTC", "SHORT", current_price, qty, current_price)
                report = f"❄️ 【空單入手中】 開倉點: ${current_price:,.2f} | 量: {qty:.4f}"

        return report
