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
    def __init__(self, symbol="BTC", initial_cash=1000, max_daily_trades=999, is_pepe=False):
        self.symbol = symbol.replace("/USDT", "")
        self.cash = initial_cash
        self.initial_budget = initial_cash # 紀錄初始資金
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
        
        # --- [自癒核心] 從資料庫恢復持倉 ---
        from core.storage import Storage
        self.db = Storage()
        self.load_active_position()
        
        # 移動回撤 (Trailing Drawdown) 參數
        self.pnl_high_water_mark = 0 # 今日盈虧最高點
        self.max_drawdown_allowed = 300 # 容許從最高點回撤 300U
        
        # 勝率過濾参數
        self.min_win_rate_to_trade = 0.60  # 最低勝率閾值 60%
        self.min_trades_for_stats = 5  # 最少需要5筆交易才能參考勝率
        
        # --- [金融改革] 借貸與預算系統 ---
        self.initial_budget = initial_cash
        self.cash = initial_cash
        self.debt_to_treasury = 0 # 向中央金庫的借款額
        self.leverage = 1.0 # AI 動態控制的槓桿
        self.last_thought = "🛰️ 正在掃描星際信號，待台中..." # 語義述職內容
        self.global_risk_level = 0 # 全球風險等級 (0-10)
        
        self.is_pepe = is_pepe
        self.is_special_fund = (symbol == "SPECIAL")
        
        self.daily_target = DailyTradeTarget(symbol, target_trades=999 if is_pepe else 15, min_winning_trades=9 if is_pepe else 12)
        
        # [同步帳務到中央]
        if storage: storage.save_global_config(f"CASH_{self.symbol}", str(self.cash))

    def request_loan_if_needed(self, storage):
        """[中央借貸機制] 如果資金低於 100U，向中央金庫借款 100U"""
        if self.cash < 100:
            loan_amt = 100
            treasury_cash = float(storage.get_global_config("TREASURY_CASH", "1000"))
            if treasury_cash >= loan_amt:
                # 執行借款
                self.cash += loan_amt
                self.debt_to_treasury += loan_amt
                storage.save_global_config("TREASURY_CASH", str(treasury_cash - loan_amt))
                storage.save_global_config(f"DEBT_{self.symbol}", str(self.debt_to_treasury))
                print(f"🏦 【中央借貸通報】 {self.symbol} 獲准撥款 {loan_amt} U，目前欠款: {self.debt_to_treasury} U")
                return True
        return False

    def auto_repay_loan(self, pnl, storage):
        """[還款機制] 獲利時優先撥出 50% 償還借款"""
        if self.debt_to_treasury > 0 and pnl > 0:
            repay_amt = min(self.debt_to_treasury, pnl * 0.5) # 分期還款 (獲利的 50%)
            self.debt_to_treasury -= repay_amt
            self.cash -= repay_amt
            
            treasury_cash = float(storage.get_global_config("TREASURY_CASH", "1000"))
            storage.save_global_config("TREASURY_CASH", str(treasury_cash + repay_amt))
            storage.save_global_config(f"DEBT_{self.symbol}", str(self.debt_to_treasury))
            return repay_amt
        return 0
    

    def load_active_position(self):
        """[自癒功能] 從資料庫讀取之前的持倉狀態"""
        try:
            pos = self.db.get_active_pos_by_symbol(self.symbol)
            if pos:
                self.position = 1 if pos['type'] == 'LONG' else -1
                self.entry_price = pos['entry_price']
                self.qty = pos['qty']
                self.trailing_high = pos['trailing_high']
                print(f"🔄 【自癒修復】 {self.symbol} 已恢復持倉: {pos['type']} @ {self.entry_price}")
            else:
                self.position = 0
                self.entry_price = 0
        except Exception as e:
            print(f"⚠️ {self.symbol} 恢復持倉失敗: {e}")

    def save_active_position(self, p_type, price, qty):
        """[監察功能] 開倉或更新進度時同步至資料庫"""
        try:
            self.db.update_active_pos(self.symbol, p_type, price, qty, self.trailing_high)
        except Exception as e:
            print(f"⚠️ {self.symbol} 儲存持倉失敗: {e}")

    def clear_active_position(self):
        """[監察功能] 平倉後清除紀錄"""
        try:
            self.db.update_active_pos(self.symbol, None, 0, 0)
        except Exception as e:
            print(f"⚠️ {self.symbol} 清除持倉失敗: {e}")

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
                confidence += 0.1
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
                report = (f"💰 【財政部稅收通報 | FAST TP】\n─────────────────\n"
                          f"🛡️ 項目: {self.symbol} (小計 40%)\n📍 執行價: ${current_price:,.2f}\n"
                          f"📈 實收盈虧: +{pnl:,.1f} U\n🏦 團隊剩餘金庫: ${self.cash:,.1f}")
                if storage: storage.log_trade(f"PT_LONG_{self.symbol}", self.entry_price, current_price, abs(self.position*0.4), pnl, self.cumulative_pnl, is_exit=True)

            self.trailing_high = max(self.trailing_high, current_price)
            if storage: storage.update_active_pos(self.symbol, "LONG", self.entry_price, self.position, self.trailing_high)
            
            # 【出場觸發點】: 
            # 1. 強制止盈 1.8% 
            # 2. RSI 極度超買 > 80 
            # 3. 跌破追蹤止損 (回撤超過 0.5 * ATR)
            # --- [智能追蹤止盈 (Trailing Stop)] ---
            # 如果當前獲利超過 1%，開始啟動追蹤止盈，止損位跟隨價格
            sl = self.entry_price * (1 - atr_sl_pct)
            if roi > 0.015: # 當獲利超過 1.5% 時啟動
            # --- [智能追蹤止盈 (Trailing Stop)] ---
            # 當獲利超過 1.5% 時，止損線跟隨價格在 0.8% 處鎖定
            sl_base = self.entry_price * (1 - atr_sl_pct)
            if roi > 0.015:
                new_stop = current_price * 0.992
                if new_stop > sl_base: sl_base = new_stop
            
            # 4. 檢查止盈 (Take Profit)
            real_sl = self.entry_price * 1.002 if self.has_partial_tp else sl_base
            
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
                
                # [自癒還款] 獲利時先還中央
                repaid = self.auto_repay_loan(pnl, storage)
                repay_msg = f"\n💸 分期還款至中央: {repaid:.1f} U (剩餘欠款: {self.debt_to_treasury:.1f} U)" if repaid > 0 else ""
                
                report = (f"✅ 【特工凱旋回鎮 | {exit_reason}】\n─────────────────\n"
                          f"🛡️ 特工: {self.symbol}\n📍 出場: ${current_price:,.4f}\n"
                          f"📉 最終盈虧: {pnl:+.1f} U\n🏦 實收現金: ${self.cash:,.1f}" + repay_msg + reflection)
                self.clear_active_position()
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
                          f"🪙 幣種: {self.symbol} (小計 40%)\n📍 價格: ${current_price:,.4f}\n"
                          f"📈 實收盈虧: +{pnl:,.1f} U\n🏦 團隊剩餘金庫: ${self.cash:,.1f}")
                if storage: storage.log_trade(f"PT_SHORT_{self.symbol}", self.entry_price, current_price, abs(self.position*0.4), pnl, self.cumulative_pnl, is_exit=True)
            
            self.trailing_low = min(self.trailing_low, current_price)
            if storage: storage.update_active_pos(self.symbol, "SHORT", self.entry_price, abs(self.position), self.trailing_low)
            
            # --- [智能追蹤止盈 (Trailing Stop)] ---
            # 空單獲利 > 1.5% 時，止損線跟隨在現價上方 0.8% 處鎖定
            sl_base = self.entry_price * (1 + atr_sl_pct)
            if roi > 0.015:
                new_stop = current_price * 1.008
                if new_stop < sl_base: sl_base = new_stop

            real_sl = self.entry_price * 0.998 if self.has_partial_tp else sl_base
            
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
                
                # [自癒還款] 獲利時先還中央
                repaid = self.auto_repay_loan(pnl, storage)
                repay_msg = f"\n💸 分期還款至中央: {repaid:.1f} U (剩餘欠款: {self.debt_to_treasury:.1f} U)" if repaid > 0 else ""

                report = (f"✅ 【平倉通報 | {exit_reason}】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol}\n📍 出場: ${current_price:,.4f}\n"
                          f"📉 最終盈虧: {pnl:+.1f} U\n🏦 實收現金: ${self.cash:,.1f}" + repay_msg + reflection)
                self.clear_active_position()
                self.position = 0
                self.has_partial_tp = False


        # --- 3. 開倉判定 ---
        if self.position == 0:
            is_sniper = True if sniper_signal == "SUPER_BUY" else False
            if self.trades_today >= self.max_daily_trades and not is_sniper:
                return "" 

            # [中央借貸檢查] 入場前若沒錢，向組長申請撥款
            if self.cash < 100:
                self.request_loan_if_needed(storage)

            # --- [AI 語義述職] 心理決策模擬 ---
            conf = context.get('ml_prob', 0.5)
            risk_alert = storage.get_global_config("GLOBAL_ALERT", "NORMAL")
            
            if risk_alert == "RED":
                self.last_thought = "🏮 [全城警報] 市場發生劇烈震盪或巨鯨大舉拋售，我已將槓桿壓制在 1x 並提高止損寬度。"
                self.leverage = 1.0
            else:
                self.leverage = 1.0 + (max(0, conf - 0.5) * 8) 
                self.leverage = min(5.0, self.leverage) 
                self.last_thought = f"📈 信心指數 {conf*100:.0f}%，目前盤勢符合我的多頭策略，決定以 {self.leverage:.1f}x 槓桿出擊。"

            if is_sniper or scalper_signal == "BUY_SCALP":
                # 指令: 均分為十等分，固定為初始預算的 10%
                invest_amt = self.initial_budget * 0.1 
                
                if self.cash < invest_amt:
                    return f"⚠️ 【分隊資金告急】{self.symbol} 現金餘額不足執行單次出擊。"
                
                # 考慮槓桿的數量 (合約模式)
                qty = (invest_amt * self.leverage) / current_price 
                self.cash -= invest_amt
                self.position = qty
                self.entry_price = current_price
                self.trailing_high = current_price
                self.has_partial_tp = False
                self.trades_today += 1
                self.save_active_position("LONG", current_price, qty)
                report = (f"🏹 【特工出擊 | LONG】\n─────────────────\n"
                          f"🛡️ 特工: {self.symbol} | 槓桿: {self.leverage:.1f}x\n📍 價格: ${current_price:,.4f}\n"
                          f"💰 保證金: ${invest_amt:,.1f} U | 名義價值: ${invest_amt*self.leverage:,.1f} U\n"
                          f"🏦 餘額: ${self.cash:,.1f} U | 欠款: ${self.debt_to_treasury:.1f} U")

            elif scalper_signal == "SELL_SCALP":
                invest_amt = self.initial_budget * 0.1
                if self.cash < invest_amt:
                    return f"⚠️ 【分隊資金告急】{self.symbol} 現金餘額不足。"
                
                qty = (invest_amt * self.leverage) / current_price
                self.cash -= invest_amt
                self.position = -qty
                self.entry_price = current_price
                self.trailing_low = current_price
                self.has_partial_tp = False
                self.trades_today += 1
                self.save_active_position("SHORT", current_price, qty)
                self.last_thought = f"📉 信心指數 {(1-conf)*100:.0f}%，判斷空頭趨勢成形，執行 {self.leverage:.1f}x 槓桿做空。"
                report = (f"❄️ 【特工出擊 | SHORT】\n─────────────────\n"
                          f"🪙 幣種: {self.symbol} | 槓桿: {self.leverage:.1f}x\n📍 價格: ${current_price:,.4f}\n"
                          f"💰 保證金: ${invest_amt:,.1f} U | 名義價值: ${invest_amt*self.leverage:,.1f} U\n"
                          f"🏦 餘額: ${self.cash:,.1f} U | 欠款: ${self.debt_to_treasury:.1f} U")

        else:
            # 觀望模式下的述職
            if context.get('ml_prob', 0.5) > 0.45 and context.get('ml_prob', 0.5) < 0.55:
                self.last_thought = "💤 市場方向不明，我決定進入潛伏狀態，節省電力與記憶體。"
            else:
                self.last_thought = "🔎 正觀察技術形態，若突破重要壓力位將立即行動。"
        
        # 保存心聲與帳務到全局
        if storage: 
            storage.save_global_config(f"THOUGHT_{self.symbol}", self.last_thought)
            storage.save_global_config(f"CASH_{self.symbol}", str(self.cash))
        return report
