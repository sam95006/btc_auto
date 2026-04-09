from datetime import datetime

class DailyTradeTarget:
    """每日交易目標追蹤"""
    def __init__(self, symbol, target_trades=15, min_winning_trades=12):
        self.symbol = symbol
        self.target_trades = target_trades
        self.min_winning_trades = min_winning_trades
        self.trades_today = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.last_day = datetime.now().day
    
    def reset_if_new_day(self):
        """新的一天時重置計數器"""
        if datetime.now().day != self.last_day:
            self.trades_today = 0
            self.winning_trades = 0
            self.losing_trades = 0
            self.last_day = datetime.now().day
    
    def record_trade(self, pnl):
        """記錄交易結果"""
        self.trades_today += 1
        if pnl > 0:
            self.winning_trades += 1
        elif pnl < 0:
            self.losing_trades += 1
    
    def get_win_rate(self):
        """獲得勝率"""
        if self.trades_today == 0:
            return 0.0
        return self.winning_trades / self.trades_today
    
    def is_target_met(self):
        """檢查是否達到日交易目標"""
        return self.trades_today >= self.target_trades and self.winning_trades >= self.min_winning_trades
    
    def get_status(self):
        """獲得今日交易狀態"""
        return {
            'symbol': self.symbol,
            'trades_today': self.trades_today,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.get_win_rate(),
            'target_trades': self.target_trades,
            'min_winning_trades': self.min_winning_trades,
            'target_met': self.is_target_met()
        }

class PaperTrader:
    def __init__(self, symbol="BTC", initial_cash=2500, max_daily_trades=999, is_pepe=False):
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
        
        # 勝率過濾参數
        self.min_win_rate_to_trade = 0.60  # 最低勝率閾值 60%
        self.min_trades_for_stats = 5  # 最少需要5筆交易才能參考勝率
        
        # 每日交易目標
        self.is_pepe = is_pepe
        if is_pepe:
            # PEPE 無限交易，但要達到 90% 勝率
            self.daily_target = DailyTradeTarget(symbol, target_trades=999, min_winning_trades=9)
        else:
            # 其他幣種每日15筆交易，12筆以上盈利
            self.daily_target = DailyTradeTarget(symbol, target_trades=15, min_winning_trades=12)
    
    def multi_timeframe_confirmation(self, m1_rsi, m15_rsi, h1_ema, current_price, direction="LONG"):
        """
        【多時間框架確認】
        返回交易信心值 (0.0-1.0)
        """
        confidence = 0.5
        
        if direction == "LONG":
            # 1min RSI < 30 (超賣)
            if m1_rsi < 30:
                confidence += 0.2
            # 15min RSI < 40 (弱勢)
            if m15_rsi < 40:
                confidence += 0.2
            # 1hour 價格在 EMA200 上方 (上升趨勢)
            if current_price > h1_ema:
                confidence += 0.1
        
        elif direction == "SHORT":
            # 1min RSI > 70 (超買)
            if m1_rsi > 70:
                confidence += 0.2
            # 15min RSI > 60 (強勢)
            if m15_rsi > 60:
                confidence += 0.2
            # 1hour 價格在 EMA200 下方 (下降趨勢)
            if current_price < h1_ema:
                confidence += 0.1
        
        return min(confidence, 1.0)
    
    def dynamic_position_sizing(self, signal_confidence, base_size=0.4, risk_per_trade=0.02):
        """
        【動態頭寸調整】
        根據信號置信度調整頭寸大小
        signal_confidence: 0.5-1.0
        Returns: 頭寸倍數 (0.2x - 0.8x)
        """
        # 映射置信度到頭寸倍數
        # 0.5 → 0.2x, 0.75 → 0.5x, 1.0 → 0.8x
        position_multiplier = 0.2 + (signal_confidence - 0.5) * 1.2
        position_multiplier = max(0.2, min(0.8, position_multiplier))
        
        position_size = base_size * (position_multiplier / 0.4)
        return position_size
    
    def advanced_trailing_exit(self, current_price, entry_price, direction="LONG"):
        """
        【高級追蹤止盈】
        3 層止盈機制:
        • +1.0% 賣出 50%
        • +1.5% 賣出 30%  
        • +2.0% 全部出場
        """
        roi = (current_price - entry_price) / entry_price if direction == "LONG" else (entry_price - current_price) / entry_price
        
        exit_actions = []
        
        if roi >= 0.020:  # 2% 利潤
            exit_actions.append({
                'action': 'FULL_EXIT',
                'pct': 100,
                'roi': roi
            })
        elif roi >= 0.015:  # 1.5% 利潤
            exit_actions.append({
                'action': 'PARTIAL_EXIT',
                'pct': 30,
                'roi': roi
            })
        elif roi >= 0.010:  # 1.0% 利潤
            exit_actions.append({
                'action': 'PARTIAL_EXIT',
                'pct': 50,
                'roi': roi
            })
        
        return exit_actions
    
    def calculate_win_rate_filtered_signal(self, base_signal_strength, historical_win_rate, min_required_rate=0.60):
        """
        【勝率過濾決策】
        如果歷史勝率低於閾值，著手降低信號強度
        """
        
        if historical_win_rate < min_required_rate:
            # 低於閾值：減弱信號
            filtered_strength = base_signal_strength * 0.5
            return {
                'take_signal': False,
                'reason': f'❌ 勝率過低 ({historical_win_rate:.1%} < {min_required_rate:.1%})',
                'adjusted_strength': filtered_strength
            }
        
        return {
            'take_signal': True,
            'reason': f'✅ 勝率達標 ({historical_win_rate:.1%})',
            'adjusted_strength': base_signal_strength
        }

    def _update_daily_target(self):
        """更新並檢查每日交易目標"""
        self.daily_target.reset_if_new_day()

    def _record_trade_result(self, pnl):
        """記錄交易結果到每日目標"""
        self.daily_target.record_trade(pnl)

    def _get_daily_status(self):
        """獲得今日交易狀態"""
        return self.daily_target.get_status()

    def execute(self, scalper_signal, sniper_signal, current_price, storage=None, atr=0, context=None):
        report = ""
        
        # 更新每日交易目標
        self._update_daily_target()
        
        now = datetime.now()
        if now.day != self.last_trade_day:
            self.trades_today = 0
            self.last_trade_day = now.day
            self.pnl_high_water_mark = 0 

        self.pnl_high_water_mark = max(self.pnl_high_water_mark, self.cumulative_pnl)
        
        if self.cumulative_pnl < (self.pnl_high_water_mark - self.max_drawdown_allowed):
            return f"🆘 【系統警告 | 風控觸發】\n{self.symbol} 已達移動回撤上限，暫停當前交易。"

        atr_sl_pct = max(0.008, (atr * 1.5) / current_price) if atr > 0 else 0.010
        
        # --- 1. 平倉與反思邏輯 (多單) ---
        if self.position > 0:
            roi = (current_price - self.entry_price) / self.entry_price
            current_rsi = context.get('rsi', 50) if context else 50
            
            # 【動態止盈】: 階梯式出場
            # 第一階段: 0.8% 且 RSI > 65 -> 出 40% (保本)
            if roi > 0.008 and current_rsi > 65 and not self.has_partial_tp:
                pnl = (current_price - self.entry_price) * (self.position * 0.4)
                self.cash += (self.entry_price * (self.position * 0.4)) + pnl
                self.cumulative_pnl += pnl
                self.position *= 0.6
                self.has_partial_tp = True
                report = (f"💰 【獲利通報 | FAST TP】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol} (小計 40%)\n📍 價格: ${current_price:,.2f}\n📈 盈虧: +{pnl:,.1f} U")
                if storage: storage.log_trade(f"PT_LONG_{self.symbol}", self.entry_price, current_price, abs(self.position*0.4), pnl, self.cumulative_pnl, is_exit=True)

            self.trailing_high = max(self.trailing_high, current_price)
            if storage: storage.update_active_pos(self.symbol, "LONG", self.entry_price, self.position, self.trailing_high)
            
            # 【出場觸發點】: 
            # 1. 強制止盈 1.8% 
            # 2. RSI 極度超買 > 80 
            # 3. 跌破追蹤止損 (回撤超過 0.5 * ATR)
            # 4. 基礎止損 (ATR 保護)
            real_sl = self.entry_price * 1.002 if self.has_partial_tp else self.entry_price * (1 - atr_sl_pct)
            
            # 獲取量能數據 (靈活變換的核心)
            relative_vol = context.get('rv', 1.0) if context else 1.0
            
            should_exit = False
            exit_reason = ""
            
            if roi > 0.018: 
                should_exit, exit_reason = True, "🎯 強制止盈"
            elif current_rsi > 80:
                should_exit, exit_reason = True, "🔥 RSI 超買"
            elif roi > 0.005 and relative_vol > 3.5:
                should_exit, exit_reason = True, "🚀 爆量見頂"
            elif abs(roi) < 0.003 and relative_vol < 0.4:
                should_exit, exit_reason = True, "💤 量能枯竭"
            elif current_price < real_sl:
                should_exit, exit_reason = True, "🛡️ 觸及止損"
            elif current_price < self.trailing_high * (1 - atr_sl_pct * 0.4):
                should_exit, exit_reason = True, "📉 追蹤滑落"

            if should_exit:
                pnl = (current_price - self.entry_price) * self.position
                self.cash += (self.entry_price * self.position) + pnl
                self.cumulative_pnl += pnl
                
                reflection = ""
                if pnl < 0 and context:
                    from learning import ReflectionEngine
                    ref_engine = ReflectionEngine(storage)
                    reflection = ref_engine.analyze_loss(self.symbol, pnl, self.entry_price, current_price, "LONG", context)
                
                if storage: storage.log_trade(f"EXIT_LONG_{self.symbol}", self.entry_price, current_price, abs(self.position), pnl, self.cumulative_pnl, is_exit=True)
                
                self._record_trade_result(pnl)
                
                report = (f"✅ 【平倉通報 | {exit_reason}】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol}\n📍 出場: ${current_price:,.2f}\n📉 盈虧: {pnl:+.1f} U" + reflection)
                self.position = 0
                self.has_partial_tp = False

        # --- 2. 平倉與反思邏輯 (空單) ---
        elif self.position < 0:
            roi = (self.entry_price - current_price) / self.entry_price
            current_rsi = context.get('rsi', 50) if context else 50
            
            # 【動態止盈】: 階梯式出場
            if roi > 0.008 and current_rsi < 35 and not self.has_partial_tp:
                pnl = (self.entry_price - current_price) * (abs(self.position) * 0.4)
                self.cash += (self.entry_price * (abs(self.position) * 0.4)) + pnl
                self.cumulative_pnl += pnl
                self.position *= 0.6
                self.has_partial_tp = True
                report = (f"💰 【獲利通報 | FAST TP】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol} (小計 40%)\n📍 價格: ${current_price:,.2f}")
                if storage: storage.log_trade(f"PT_SHORT_{self.symbol}", self.entry_price, current_price, abs(self.position*0.4), pnl, self.cumulative_pnl, is_exit=True)
            
            self.trailing_low = min(self.trailing_low, current_price)
            if storage: storage.update_active_pos(self.symbol, "SHORT", self.entry_price, abs(self.position), self.trailing_low)
            
            real_sl = self.entry_price * 0.998 if self.has_partial_tp else self.entry_price * (1 + atr_sl_pct)
            
            # 獲取量能數據
            relative_vol = context.get('rv', 1.0) if context else 1.0
            
            should_exit = False
            exit_reason = ""
            
            if roi > 0.018:
                should_exit, exit_reason = True, "🎯 強制止盈"
            elif current_rsi < 20:
                should_exit, exit_reason = True, "🔥 RSI 超賣"
            elif roi > 0.005 and relative_vol > 3.5:
                should_exit, exit_reason = True, "🚀 爆量見底"
            elif abs(roi) < 0.003 and relative_vol < 0.4:
                should_exit, exit_reason = True, "💤 量能枯竭"
            elif current_price > real_sl:
                should_exit, exit_reason = True, "🛡️ 觸及止損"
            elif current_price > self.trailing_low * (1 + atr_sl_pct * 0.4):
                should_exit, exit_reason = True, "📉 追蹤滑落"

            if should_exit:
                pnl = (self.entry_price - current_price) * abs(self.position)
                self.cash += (self.entry_price * abs(self.position)) + pnl
                self.cumulative_pnl += pnl
                
                reflection = ""
                if pnl < 0 and context:
                    from learning import ReflectionEngine
                    ref_engine = ReflectionEngine(storage)
                    reflection = ref_engine.analyze_loss(self.symbol, pnl, self.entry_price, current_price, "SHORT", context)

                if storage: storage.log_trade(f"EXIT_SHORT_{self.symbol}", self.entry_price, current_price, abs(self.position), pnl, self.cumulative_pnl, is_exit=True)
                
                self._record_trade_result(pnl)
                
                report = (f"✅ 【平倉通報 | {exit_reason}】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol}\n📍 出場: ${current_price:,.2f}\n📉 盈虧: {pnl:+.1f} U" + reflection)
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
