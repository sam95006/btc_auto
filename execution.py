class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0
        self.entry_price = 0
        self.cumulative_pnl = initial_cumulative_pnl
        self.trailing_high = 0
        self.trailing_low = 0
        self.has_partial_tp = False 
        self.max_daily_drawdown = -500

    def execute(self, scalper_signal, sniper_signal, current_price, storage=None, atr=0):
        report = ""
        if self.cumulative_pnl < self.max_daily_drawdown:
            return "🆘 [斷路器] 觸發日損極限，冷卻中..."

        atr_sl_pct = max(0.015, (atr * 2.5) / current_price) if atr > 0 else 0.015
        
        # --- 1. 平倉與分批獲利邏輯 (多單) ---
        if self.position > 0:
            roi = (current_price - self.entry_price) / self.entry_price
            # [分批獲利 30%]: 獲利達標先出一半
            if roi > 0.03 and not self.has_partial_tp:
                pnl = (current_price - self.entry_price) * (self.position / 2)
                self.cash += (self.entry_price * (self.position / 2)) + pnl
                self.cumulative_pnl += pnl
                self.position /= 2
                self.has_partial_tp = True
                report = f"💰 【!!獲利達標!! 出貨一半】\n📍 離場點: ${current_price:,.2f} | 盈虧: +{pnl:,.2f} U\n🛡️ 剩餘倉位已設為「成本價保護」。"
                if storage: storage.log_trade("PARTIAL_EXIT_LONG", current_price, abs(self.position), pnl, self.cumulative_pnl)
            
            self.trailing_high = max(self.trailing_high, current_price)
            if storage: storage.update_active_pos("BTC", "LONG", self.entry_price, self.position, self.trailing_high)
            
            # 若已分批獲利，止損鎖死在成本價
            real_sl = self.entry_price if self.has_partial_tp else self.entry_price * (1 - atr_sl_pct)
            if current_price < real_sl or current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade("EXIT_LONG", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos("BTC", "NONE", 0, 0)
                
                # 計算盈虧率
                pnl_rate = (current_price - self.entry_price) / self.entry_price * 100
                invested_u = self.entry_price * self.position
                report = (f"✅ 【多單精確平倉】\n"
                          f"🔹 出場點位: ${current_price:,.2f}\n"
                          f"🔸 進場點位: ${self.entry_price:,.2f}\n"
                          f"💰 下單金額: {invested_u:,.2f} U\n"
                          f"📉 單筆盈虧: {'+' if pnl>0 else ''}{pnl:,.2f} U\n"
                          f"📊 盈虧率: {pnl_rate:+.2f}%\n"
                          f"🏦 剩餘可用本金: {self.cash:,.2f} U")
                self.position = 0
                self.has_partial_tp = False

        # --- 2. 平倉與分批獲利邏輯 (空單) ---
        elif self.position < 0:
            roi = (self.entry_price - current_price) / self.entry_price
            if roi > 0.03 and not self.has_partial_tp:
                pnl = (self.entry_price - current_price) * (abs(self.position) / 2)
                self.cash += (self.entry_price * (abs(self.position) / 2)) + pnl
                self.cumulative_pnl += pnl
                self.position /= 2
                self.has_partial_tp = True
                report = f"💰 【!!做空獲利達標!!】\n📍 離場點: ${current_price:,.2f} | 盈虧: +{pnl:,.2f} U\n🛡️ 剩餘空單保護中..."
                if storage: storage.log_trade("PARTIAL_EXIT_SHORT", current_price, abs(self.position), pnl, self.cumulative_pnl)
            
            self.trailing_low = min(self.trailing_low, current_price)
            if storage: storage.update_active_pos("BTC", "SHORT", self.entry_price, abs(self.position), self.trailing_low)
            
            real_sl = self.entry_price if self.has_partial_tp else self.entry_price * (1 + atr_sl_pct)
            if current_price > real_sl or current_price > self.trailing_low * (1 + atr_sl_pct * 0.5):
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade("EXIT_SHORT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos("BTC", "NONE", 0, 0)
                
                # 計算盈虧率
                pnl_rate = (self.entry_price - current_price) / self.entry_price * 100
                invested_u = self.entry_price * abs(self.position)
                report = (f"✅ 【空單精確平倉】\n"
                          f"🔹 出場點位: ${current_price:,.2f}\n"
                          f"🔸 進場點位: ${self.entry_price:,.2f}\n"
                          f"💰 下單金額: {invested_u:,.2f} U\n"
                          f"📉 單筆盈虧: {'+' if pnl>0 else ''}{pnl:,.2f} U\n"
                          f"📊 盈虧率: {pnl_rate:+.2f}%\n"
                          f"🏦 剩餘可用本金: {self.cash:,.2f} U")
                self.position = 0
                self.has_partial_tp = False

        # --- 3. 雙擎開倉判定 ---
        if self.position == 0:
            if sniper_signal == "SUPER_BUY":
                qty = (self.cash * 0.35) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                self.has_partial_tp = False
                if storage: storage.update_active_pos("BTC", "LONG_SNIPER", current_price, qty, current_price)
                report = f"🎯 【極限狙擊：重倉出擊】\n📍 買入: ${current_price:,.2f} | 35% 部位"

            elif scalper_signal == "BUY_SCALP":
                qty = (self.cash * 0.1) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                self.has_partial_tp = False
                if storage: storage.update_active_pos("BTC", "LONG_SCALP", current_price, qty, current_price)
                report = f"⚡ 【高頻突擊：輕倉做多】\n📍 買入: ${current_price:,.2f} | 10% 部位"

            elif scalper_signal == "SELL_SCALP":
                qty = (self.cash * 0.1) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                self.has_partial_tp = False
                if storage: storage.update_active_pos("BTC", "SHORT_SCALP", current_price, qty, current_price)
                report = f"❄️ 【高頻突擊：做空試探】\n📍 賣出: ${current_price:,.2f} | 10% 部位"

        return report
