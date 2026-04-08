from datetime import datetime

class PaperTrader:
    def __init__(self, symbol="BTC", initial_cash=2500, max_daily_trades=999):
        self.symbol = symbol.replace("/USDT", "")
        self.cash = initial_cash
        self.position = 0
        self.entry_price = 0
        self.cumulative_pnl = 0
        self.trailing_high = 0
        self.trailing_low = 0
        self.has_partial_tp = False 
        self.max_daily_drawdown = -500
        
        # 次數控管
        self.max_daily_trades = max_daily_trades
        self.trades_today = 0
        self.last_trade_day = datetime.now().day

    def execute(self, scalper_signal, sniper_signal, current_price, storage=None, atr=0):
        report = ""
        
        # 每日次數重置
        now = datetime.now()
        if now.day != self.last_trade_day:
            self.trades_today = 0
            self.last_trade_day = now.day

        if self.cumulative_pnl < self.max_daily_drawdown:
            return f"🆘 [{self.symbol}] 觸發斷路器，暫停交易。"

        atr_sl_pct = max(0.012, (atr * 2.0) / current_price) if atr > 0 else 0.012
        
        # --- 1. 平倉邏輯 ---
        if self.position > 0:
            roi = (current_price - self.entry_price) / self.entry_price
            if roi > 0.015 and not self.has_partial_tp:
                pnl = (current_price - self.entry_price) * (self.position / 2)
                self.cash += (self.entry_price * (self.position / 2)) + pnl
                self.cumulative_pnl += pnl
                self.position /= 2
                self.has_partial_tp = True
                report = f"💰 【{self.symbol} 獲利 50% 出貨】\n📍 點位: ${current_price:,.2f} | 盈虧: +{pnl:,.2f} U"
                if storage: storage.log_trade(f"PARTIAL_EXIT_LONG_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
            
            self.trailing_high = max(self.trailing_high, current_price)
            if storage: storage.update_active_pos(self.symbol, "LONG", self.entry_price, self.position, self.trailing_high)
            
            real_sl = self.entry_price if self.has_partial_tp else self.entry_price * (1 - atr_sl_pct)
            if roi > 0.025 or current_price < real_sl or current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade(f"EXIT_LONG_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos(self.symbol, "NONE", 0, 0)
                
                report = f"✅ 【{self.symbol} 多單平倉】\n🔹 出場: ${current_price:,.2f}\n📉 盈虧: {pnl:+.2f} U | 餘額: {self.cash:,.1f} U"
                self.position = 0
                self.has_partial_tp = False

        elif self.position < 0:
            roi = (self.entry_price - current_price) / self.entry_price
            if roi > 0.015 and not self.has_partial_tp:
                pnl = (self.entry_price - current_price) * (abs(self.position) / 2)
                self.cash += (self.entry_price * (abs(self.position) / 2)) + pnl
                self.cumulative_pnl += pnl
                self.position /= 2
                self.has_partial_tp = True
                report = f"💰 【{self.symbol} 空單獲利 50% 出兵】\n📍 點位: ${current_price:,.2f} | 盈虧: +{pnl:,.2f} U"
                if storage: storage.log_trade(f"PARTIAL_EXIT_SHORT_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
            
            self.trailing_low = min(self.trailing_low, current_price)
            if storage: storage.update_active_pos(self.symbol, "SHORT", self.entry_price, abs(self.position), self.trailing_low)
            
            real_sl = self.entry_price if self.has_partial_tp else self.entry_price * (1 + atr_sl_pct)
            if roi > 0.025 or current_price > real_sl or current_price > self.trailing_low * (1 + atr_sl_pct * 0.5):
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    storage.log_trade(f"EXIT_SHORT_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    storage.update_active_pos(self.symbol, "NONE", 0, 0)
                
                report = f"✅ 【{self.symbol} 空單平倉】\n🔹 出場: ${current_price:,.2f}\n📉 盈虧: {pnl:+.2f} U | 餘額: {self.cash:,.1f} U"
                self.position = 0
                self.has_partial_tp = False

        # --- 2. 開倉判定 ---
        if self.position == 0:
            # 次數檢查
            if self.trades_today >= self.max_daily_trades:
                return "" # 超過今日限額，不出聲

            if sniper_signal == "SUPER_BUY" or scalper_signal == "BUY_SCALP":
                qty = (self.cash * 0.4) / current_price # 每隻幣動用自己的 40% 資金
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                self.has_partial_tp = False
                self.trades_today += 1
                if storage: 
                    storage.update_active_pos(self.symbol, "LONG", current_price, qty, current_price)
                    storage.log_trade(f"ENTRY_LONG_{self.symbol}", current_price, qty, 0, self.cumulative_pnl)
                report = f"🎯 【{self.symbol} 進場開多】\n📍 點位: ${current_price:,.4f}\n📊 今日已出戰 {self.trades_today} 次"

            elif scalper_signal == "SELL_SCALP":
                qty = (self.cash * 0.4) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                self.has_partial_tp = False
                self.trades_today += 1
                if storage: 
                    storage.update_active_pos(self.symbol, "SHORT", current_price, qty, current_price)
                    storage.log_trade(f"ENTRY_SHORT_{self.symbol}", current_price, qty, 0, self.cumulative_pnl)
                report = f"❄️ 【{self.symbol} 進場開空】\n📍 點位: ${current_price:,.4f}\n📊 今日已出戰 {self.trades_today} 次"

        return report
