class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0          # 負數代表「做空 (Short)」, 正數代表「做多 (Long)」
        self.entry_price = 0
        self.cumulative_pnl = initial_cumulative_pnl
        # 追蹤止損參數
        self.highest_price = 0
        self.lowest_price = 999999
        self.trailing_percent = 0.015 # 1.5% 追蹤回徹則平倉

    def execute(self, signal, current_price, storage):
        report = ""
        
        # --- 追蹤止利/止損邏輯 (動能補救) ---
        if self.position > 0: # 多單中
            self.highest_price = max(self.highest_price, current_price)
            # 如果價格從最高點回落超過 1.5% -> 強制出場鎖利
            if current_price < self.highest_price * (1 - self.trailing_percent):
                return self._exit_position(current_price, storage, "TSL_LONG_EXIT")
        
        elif self.position < 0: # 空單中
            self.lowest_price = min(self.lowest_price, current_price)
            # 如果價格從最低點回升超過 1.5% -> 強制出場鎖利/止損
            if current_price > self.lowest_price * (1 + self.trailing_percent):
                return self._exit_position(current_price, storage, "TSL_SHORT_EXIT")

        # --- 訊號執行與反向補救邏輯 ---
        if signal == "BUY" and self.position <= 0:
            if self.position < 0:
                report += self._exit_position(current_price, storage, "REMEDY_COVER")
            
            buy_amount = (self.cash * 0.98) / current_price
            self.position = buy_amount
            self.entry_price = current_price
            self.highest_price = current_price
            self.cash -= (self.position * current_price)
            storage.log_trade("BUY_LONG", current_price, self.position, 0, self.cumulative_pnl)
            report += f"🚀 [模擬多單進場] 價格: ${current_price:,.2f}"
            return report

        elif signal == "SELL" and self.position >= 0:
            if self.position > 0:
                report += self._exit_position(current_price, storage, "REMEDY_SELL")
            
            short_amount = (self.cash * 0.98) / current_price
            self.position = -short_amount
            self.entry_price = current_price
            self.lowest_price = current_price
            storage.log_trade("OPEN_SHORT", current_price, abs(self.position), 0, self.cumulative_pnl)
            report += f"🔻 [模擬空單進場] 價格: ${current_price:,.2f}"
            return report

        return None

    def _exit_position(self, current_price, storage, exit_type):
        if self.position > 0:
            pnl = (current_price - self.entry_price) * self.position
            self.cash += (self.position * current_price)
        else:
            pnl = (self.entry_price - current_price) * abs(self.position)
            self.cash += (self.entry_price * abs(self.position)) + pnl
            
        self.cumulative_pnl += pnl
        storage.log_trade(exit_type, current_price, abs(self.position), pnl, self.cumulative_pnl)
        old_pos = self.position
        self.position = 0
        self.entry_price = 0
        status = "獲利" if pnl > 0 else "補救/虧損"
        return f"🏁 [{exit_type}] {status}: ${pnl:,.2f} | "
