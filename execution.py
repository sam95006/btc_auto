class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0          # 負數: 做空 (Short), 正數: 做多 (Long)
        self.entry_price = 0
        self.cumulative_pnl = initial_cumulative_pnl
        self.trailing_high = 0
        self.trailing_low = 0

    def execute(self, signal, current_price, storage=None, ml_prob=0.5, atr=0):
        report = ""
        # 動態止盈止損閾值 (ATR 兩倍作為安全緩衝)
        # 固定最小 1% 止損，或使用 2.5x ATR
        atr_sl_pct = max(0.015, (atr * 2.5) / current_price) if atr > 0 else 0.015
        
        # 1. 檢查是否需要觸發「追蹤止盈」或「止損」
        if self.position > 0: # 多單中
            self.trailing_high = max(self.trailing_high, current_price)
            # 追蹤回撤判定 (自適應寬度)
            if current_price < self.entry_price * (1 - atr_sl_pct) or \
               current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    try: storage.log_trade("TSL_LONG_EXIT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    except: pass
                report = f"✅ [多單追蹤止盈] 點位: ${current_price:,.2f} | 獲利: ${pnl:,.2f} | 累積: ${self.cumulative_pnl:,.2f}"
                self.position = 0

        elif self.position < 0: # 空單中
            self.trailing_low = min(self.trailing_low, current_price)
            if current_price > self.entry_price * (1 + atr_sl_pct) or \
               current_price > self.trailing_low * (1 + atr_sl_pct * 0.5):
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    try: storage.log_trade("TSL_SHORT_EXIT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    except: pass
                report = f"✅ [空單追蹤平倉] 點位: ${current_price:,.2f} | 獲利: ${pnl:,.2f} | 累積: ${self.cumulative_pnl:,.2f}"
                self.position = 0

        # 2. 開倉判定 (僅在無持倉時根據超高勝率進場)
        if self.position == 0:
            # 只有 AI 信心機率高於 75% 且與技術指標共振時才進場
            if signal == "BUY" and ml_prob > 0.75:
                # 簡單倉位管理：使用現金的 10% 做一次進場 (保守策略)
                qty = (self.cash * 0.1) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                if storage:
                    try: storage.log_trade("BUY_LONG", current_price, qty, 0, self.cumulative_pnl)
                    except: pass
                report = f"🔥 [猛龍進場] 多單開倉: ${current_price:,.2f} | AI信心: {ml_prob:.1%}"

            elif signal == "SELL" and ml_prob < 0.25: # 代表極度看跌機率高
                qty = (self.cash * 0.1) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                if storage:
                    try: storage.log_trade("OPEN_SHORT", current_price, qty, 0, self.cumulative_pnl)
                    except: pass
                report = f"❄️ [寒蟬冷空] 空單開倉: ${current_price:,.2f} | AI跌勢信心: {(1-ml_prob):.1%}"

        return report
