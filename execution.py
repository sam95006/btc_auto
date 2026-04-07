class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0
        self.entry_price = 0
        self.cumulative_pnl = initial_cumulative_pnl
        self.trailing_high = 0
        self.trailing_low = 0
        self.max_daily_drawdown = -500 # 容許較大的波動範圍

    def execute(self, scalper_signal, sniper_signal, current_price, storage=None, atr=0):
        report = ""
        if self.cumulative_pnl < self.max_daily_drawdown:
            return "🆘 [斷路器] 觸發日損極限，冷卻中..."

        atr_sl_pct = max(0.015, (atr * 2.5) / current_price) if atr > 0 else 0.015
        
        # --- 1. 平倉邏輯 (動態止損/追蹤止盈) ---
        if self.position > 0:
            self.trailing_high = max(self.trailing_high, current_price)
            if storage: storage.update_active_pos("BTC", "LONG", self.entry_price, self.position, self.trailing_high)
            
            if current_price < self.entry_price * (1 - atr_sl_pct) or \
               current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade("EXIT_LONG", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos("BTC", "NONE", 0, 0)
                report = f"✅ 【多單精確平倉】\n🔹 出場點位: ${current_price:,.2f}\n🔸 進場點位: ${self.entry_price:,.2f}\n💰 單筆盈虧: ${pnl:,.2f}"
                self.position = 0

        elif self.position < 0:
            self.trailing_low = min(self.trailing_low, current_price)
            if storage: storage.update_active_pos("BTC", "SHORT", self.entry_price, abs(self.position), self.trailing_low)
            
            if current_price > self.entry_price * (1 + atr_sl_pct) or \
               current_price > self.trailing_low * (1 + atr_sl_pct * 0.5):
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade("EXIT_SHORT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos("BTC", "NONE", 0, 0)
                report = f"✅ 【空單精確平倉】\n🔹 出場點位: ${current_price:,.2f}\n🔸 進場點位: ${self.entry_price:,.2f}\n💰 單筆盈虧: ${pnl:,.2f}"
                self.position = 0

        # --- 2. 雙擎開倉邏輯 ---
        if self.position == 0:
            # 優先處理神風狙擊手訊號 (重倉 35%)
            if sniper_signal == "SUPER_BUY":
                qty = (self.cash * 0.35) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                if storage: 
                    storage.update_active_pos("BTC", "LONG_SNIPER", current_price, qty, current_price)
                    storage.log_trade("ENTRY_LONG_SNIPER", current_price, qty, 0, self.cumulative_pnl)
                report = f"🎯 【極限狙擊：重倉出擊】\n📍 買入點位: ${current_price:,.2f}\n📊 倉位佔比: 35% (勝率 > 80%)\n宏觀與技術共振，資金全線進場！"

            # 處理突擊部隊訊號 (輕倉 10%)
            elif scalper_signal == "BUY_SCALP":
                qty = (self.cash * 0.1) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                if storage:
                    storage.update_active_pos("BTC", "LONG_SCALP", current_price, qty, current_price)
                    storage.log_trade("ENTRY_LONG_SCALP", current_price, qty, 0, self.cumulative_pnl)
                report = f"⚡ 【高頻突擊：輕倉試探】\n📍 買入點位: ${current_price:,.2f}\n📊 倉位佔比: 10% (勝率 > 60%)"

            elif scalper_signal == "SELL_SCALP":
                qty = (self.cash * 0.1) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                if storage:
                    storage.update_active_pos("BTC", "SHORT_SCALP", current_price, qty, current_price)
                    storage.log_trade("ENTRY_SHORT_SCALP", current_price, qty, 0, self.cumulative_pnl)
                report = f"❄️ 【高頻突擊：做空試探】\n📍 賣出點位: ${current_price:,.2f}\n📊 倉位佔比: 10% (勝率 > 60%)"

        return report
