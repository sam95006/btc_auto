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
        
        self.max_daily_trades = max_daily_trades
        self.trades_today = 0
        self.last_trade_day = datetime.now().day
        
        # 移動回撤 (Trailing Drawdown) 參數
        self.pnl_high_water_mark = 0 # 今日盈虧最高點
        self.max_drawdown_allowed = 300 # 容許從最高點回撤 300U

    def execute(self, scalper_signal, sniper_signal, current_price, storage=None, atr=0, context=None):
        report = ""
        now = datetime.now()
        if now.day != self.last_trade_day:
            self.trades_today = 0
            self.last_trade_day = now.day
            self.pnl_high_water_mark = 0 

        self.pnl_high_water_mark = max(self.pnl_high_water_mark, self.cumulative_pnl)
        
        if self.cumulative_pnl < (self.pnl_high_water_mark - self.max_drawdown_allowed):
            return f"🆘 【系統警告 | 風控觸發】\n{self.symbol} 已達移動回撤上限，暫停當前交易。"

        atr_sl_pct = max(0.012, (atr * 2.0) / current_price) if atr > 0 else 0.012
        
        # --- 1. 平倉與反思邏輯 (多單) ---
        if self.position > 0:
            roi = (current_price - self.entry_price) / self.entry_price
            if roi > 0.015 and not self.has_partial_tp:
                pnl = (current_price - self.entry_price) * (self.position / 2)
                self.cash += (self.entry_price * (self.position / 2)) + pnl
                self.cumulative_pnl += pnl
                self.position /= 2
                self.has_partial_tp = True
                report = (f"💰 【獲利通報 | PARTIAL TP】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol} (50% 出貨)\n📍 價格: ${current_price:,.2f}\n📈 盈虧: +{pnl:,.1f} U")
                if storage: storage.log_trade(f"PT_LONG_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
            
            self.trailing_high = max(self.trailing_high, current_price)
            if storage: storage.update_active_pos(self.symbol, "LONG", self.entry_price, self.position, self.trailing_high)
            
            real_sl = self.entry_price if self.has_partial_tp else self.entry_price * (1 - atr_sl_pct)
            if roi > 0.025 or current_price < real_sl or current_price < self.trailing_high * (1 - atr_sl_pct * 0.5):
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                
                reflection = ""
                if pnl < 0 and context:
                    from learning import ReflectionEngine
                    ref_engine = ReflectionEngine(storage)
                    reflection = ref_engine.analyze_loss(self.symbol, pnl, self.entry_price, current_price, "LONG", context)
                
                if storage: storage.log_trade(f"EXIT_LONG_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
                
                report = (f"✅ 【平倉通報 | TRADE CLOSED】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol} (多單離場)\n📍 出場: ${current_price:,.2f}\n📉 盈虧: {pnl:+.1f} U" + reflection)
                self.position = 0
                self.has_partial_tp = False

        # --- 2. 平倉與反思邏輯 (空單) ---
        elif self.position < 0:
            roi = (self.entry_price - current_price) / self.entry_price
            if roi > 0.015 and not self.has_partial_tp:
                pnl = (self.entry_price - current_price) * (abs(self.position) / 2)
                self.cash += (self.entry_price * (abs(self.position) / 2)) + pnl
                self.cumulative_pnl += pnl
                self.position /= 2
                self.has_partial_tp = True
                report = (f"💰 【獲利通報 | PARTIAL TP】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol} (50% 出貨)\n📍 價格: ${current_price:,.2f}")
                if storage: storage.log_trade(f"PT_SHORT_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
            
            self.trailing_low = min(self.trailing_low, current_price)
            if storage: storage.update_active_pos(self.symbol, "SHORT", self.entry_price, abs(self.position), self.trailing_low)
            
            real_sl = self.entry_price if self.has_partial_tp else self.entry_price * (1 + atr_sl_pct)
            if roi > 0.025 or current_price > real_sl or current_price > self.trailing_low * (1 + atr_sl_pct * 0.5):
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                
                reflection = ""
                if pnl < 0 and context:
                    from learning import ReflectionEngine
                    ref_engine = ReflectionEngine(storage)
                    reflection = ref_engine.analyze_loss(self.symbol, pnl, self.entry_price, current_price, "SHORT", context)

                if storage: storage.log_trade(f"EXIT_SHORT_{self.symbol}", current_price, abs(self.position), pnl, self.cumulative_pnl)
                
                report = (f"✅ 【平倉通報 | TRADE CLOSED】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol} (空單離場)\n📍 出場: ${current_price:,.2f}\n📉 盈虧: {pnl:+.1f} U" + reflection)
                self.position = 0
                self.has_partial_tp = False

        # --- 3. 開倉判定 (加入 AI 反思比對) ---
        if self.position == 0:
            is_sniper = True if sniper_signal == "SUPER_BUY" else False
            if self.trades_today >= self.max_daily_trades and not is_sniper:
                return "" 

            # AI 反思比對 (防錯)
            if context and storage:
                from learning import ReflectionEngine
                ref_engine = ReflectionEngine(storage)
                is_danger, reason = ref_engine.is_similar_to_failed_trade(self.symbol, context)
                if is_danger:
                    return f"🛡️ 【AI 攔截 | REFLECTION】\n{self.symbol} 當前環境與歷史虧損案例極度相似，已自動取消進場以規避風險。\n過去原因: {reason}"

            if is_sniper or scalper_signal == "BUY_SCALP":
                qty = (self.cash * 0.4) / current_price 
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                self.has_partial_tp = False
                self.trades_today += 1
                if storage: storage.log_trade(f"EN_LONG_{self.symbol}", current_price, qty, 0, self.cumulative_pnl)
                report = (f"🎯 【開倉通報 | LONG ENTRY】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol}\n📍 價格: ${current_price:,.4f}\n🧠 AI 信心: {context.get('ml_prob', 0)*100:.0f}%\n🛡️ 風險: ATR 保護中")

            elif scalper_signal == "SELL_SCALP":
                qty = (self.cash * 0.4) / current_price
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                self.has_partial_tp = False
                self.trades_today += 1
                if storage: storage.log_trade(f"EN_SHORT_{self.symbol}", current_price, qty, 0, self.cumulative_pnl)
                report = (f"❄️ 【開倉通報 | SHORT ENTRY】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol}\n📍 價格: ${current_price:,.4f}\n🧠 AI 信心: {(1-context.get('ml_prob', 1))*100:.0f}%\n🛡️ 風險: ATR 保護中")

        return report

        return report
