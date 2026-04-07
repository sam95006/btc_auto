class PaperTrader:
    def __init__(self, initial_cash=10000, initial_cumulative_pnl=0):
        self.cash = initial_cash
        self.position = 0          # 負數代表「做空 (Short)」, 正數代表「做多 (Long)」
        self.entry_price = 0
        self.cumulative_pnl = initial_cumulative_pnl

    def execute(self, signal, current_price, storage):
        report = ""
        
        # 1. 偵測到「做多」訊號 (且目前沒開多單)
        if signal == "BUY" and self.position <= 0:
            # 如果目前有「空單」，先平倉空單
            if self.position < 0:
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                storage.log_trade("COVER_SHORT", current_price, abs(self.position), pnl, self.cumulative_pnl)
                report += f"⏬ [空單平倉] 獲利: ${pnl:,.2f} | "

            # 開啟新多單
            buy_amount = (self.cash * 0.98) / current_price  # 留2%緩衝
            self.position = buy_amount
            self.entry_price = current_price
            self.cash -= (self.position * current_price)
            storage.log_trade("BUY_LONG", current_price, self.position, 0, self.cumulative_pnl)
            report += f"🚀 [模擬多單] 價格: ${current_price:,.2f} | 數量: {self.position:.6f}"
            return report

        # 2. 偵測到「做空」訊號 (且目前沒開空單)
        elif signal == "SELL" and self.position >= 0:
            # 如果目前有「多單」，先平倉多單
            if self.position > 0:
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.position * current_price)
                self.cumulative_pnl += pnl
                storage.log_trade("SELL_LONG", current_price, self.position, pnl, self.cumulative_pnl)
                report += f"✔️ [多單平倉] 獲利: ${pnl:,.2f} | "

            # 開啟新空單 (模擬開空)
            short_amount = (self.cash * 0.98) / current_price
            self.position = -short_amount  # 表示空單
            self.entry_price = current_price
            # 自留現金 100% 作為保證金模擬，實際上 cash 先扣除模擬金額
            storage.log_trade("OPEN_SHORT", current_price, abs(self.position), 0, self.cumulative_pnl)
            report += f"🔻 [模擬空單] 價格: ${current_price:,.2f} | 數量: {abs(self.position):.6f}"
            return report

        return None
