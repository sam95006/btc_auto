class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0          # 負數: 做空 (Short), 正數: 做多 (Long)
        self.entry_price = 0
        self.entry_qty = 0
        self.cumulative_pnl = initial_cumulative_pnl
        self.trailing_high = 0
        self.trailing_low = 0

    def execute(self, signal, current_price, storage=None, ml_prob=0.5, atr=0):
        report = ""
        atr_sl_pct = max(0.015, (atr * 2.5) / current_price) if atr > 0 else 0.015
        
        # 1. 檢查是否需要觸發「追蹤止盈」或「止損」
        if self.position > 0: # 多單中
            self.trailing_high = max(self.trailing_high, current_price)
            # 追蹤回撤判定
            if current_price < self.entry_price * (1 - atr_sl_pct) or \
               current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                if storage:
                    try: storage.log_trade("TSL_LONG_EXIT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                    except: pass
                report = (f"✅ 【多單平倉】\n"
                          f"🔹 出場點: ${current_price:,.2f}\n"
                          f"🔹 入場點: ${self.entry_price:,.2f}\n"
                          f"🔹 下單量: {abs(self.position):.4f}\n"
                          f"💰 單筆盈虧: ${pnl:,.2f}\n"
                          f"🏆 累積帳戶: ${self.cumulative_pnl:,.2f}")
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
                report = (f"✅ 【空單平倉】\n"
                          f"🔹 出場點: ${current_price:,.2f}\n"
                          f"🔹 入場點: ${self.entry_price:,.2f}\n"
                          f"🔹 下單量: {abs(self.position):.4f}\n"
                          f"💰 單筆盈虧: ${pnl:,.2f}\n"
                          f"🏆 累積帳戶: ${self.cumulative_pnl:,.2f}")
                self.position = 0

        # 2. 開倉判定
        if self.position == 0:
            if signal == "BUY" and ml_prob > 0.75:
                qty = (self.cash * 0.1) / current_price
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                if storage:
                    try: storage.log_trade("BUY_LONG", current_price, qty, 0, self.cumulative_pnl)
                    except: pass
                report = (f"🔥 【多單進場】\n"
                          f"🔸 幣種: BTC/USDT\n"
                          f"🔸 進場點: ${current_price:,.2f}\n"
                          f"🔸 下單量: {qty:.4f}\n"
                          f"🧠 AI 信心: {ml_prob:.1%}")

            elif signal == "SELL" and ml_prob < 0.25:
                qty = (self.cash * 0.1) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                if storage:
                    try: storage.log_trade("OPEN_SHORT", current_price, qty, 0, self.cumulative_pnl)
                    except: pass
                report = (f"❄️ 【空單進場】\n"
                          f"🔸 幣種: BTC/USDT\n"
                          f"🔸 進場點: ${current_price:,.2f}\n"
                          f"🔸 下單量: {qty:.4f}\n"
                          f"🧠 AI 信心: {(1-ml_prob):.1%}")

        return report
