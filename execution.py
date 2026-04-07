class PaperTrader:
    def __init__(self, initial_balance=10000, initial_cumulative_pnl=0):
        self.balance = initial_balance  # 目前虛擬現金
        self.position = 0               # 持有 BTC 數量
        self.entry_price = 0            # 進場平均價
        self.cumulative_pnl = initial_cumulative_pnl  # 累積損益 (歷史繼承)

    def execute(self, signal, price, storage):
        msg = None
        
        # 買入邏輯: 如果目前空倉 且 收到 BUY 訊號
        if signal == 'BUY' and self.position == 0:
            self.position = self.balance / price
            self.entry_price = price
            self.balance = 0
            storage.log_trade('BUY', price, self.position, 0, self.cumulative_pnl)
            msg = f"🚀 [模擬買入] 價格: ${price:,.2f} | 倉位數量: {self.position:.6f}"

        # 賣出邏輯: 如果目前持倉 且 收到 SELL 訊號
        elif signal == 'SELL' and self.position > 0:
            sale_value = self.position * price
            pnl = sale_value - (self.position * self.entry_price)
            self.cumulative_pnl += pnl
            self.balance = sale_value
            storage.log_trade('SELL', price, self.position, pnl, self.cumulative_pnl)
            
            msg = (f"🔻 [模擬賣出] 價格: ${price:,.2f} | "
                   f"單次損益: ${pnl:,.2f} | "
                   f"累積損益: ${self.cumulative_pnl:,.2f}")
            
            self.position = 0
            self.entry_price = 0
            
        return msg
