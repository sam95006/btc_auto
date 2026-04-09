from strategy.learning import AdaptiveMLPredictor
from datetime import datetime

class ExpertAgent:
    """專家特工: 負責特定維度的數據分析"""
    def __init__(self, name, personality, symbol, storage):
        self.name = name
        self.personality = personality # 'AGGRESSIVE', 'STEADY', 'RISK_GUARD'
        self.symbol = symbol
        self.storage = storage
        self.predictor = AdaptiveMLPredictor(symbol=f"{symbol}_{name}", storage=storage)

    def analyze(self, df_1m, df_15m, market_context):
        """專家根據自己的性格給出建議 (嚴格 7 成勝率過濾版)"""
        prob = self.predictor.predict_prob(df_1m.iloc[-1], market_context=market_context)
        
        # Binance 交易量與指標取值
        current_price = df_1m.iloc[-1]['close']
        vol = df_1m.iloc[-1]['volume']
        vol_ma = df_1m['volume'].rolling(20).mean().iloc[-1]
        vol_breakout = vol > (vol_ma * 1.5) if vol_ma > 0 else False
        rsi_1m = df_1m.iloc[-1].get('RSI', 50)
        
        if self.personality == 'AGGRESSIVE':
            # 激進派 (Scalper)：但升級為 7 成勝率指標，需量能突破且 RSI 極端
            if prob >= 0.70 and rsi_1m < 35 and vol_breakout: 
                return "BUY", prob
            if prob <= 0.30 and rsi_1m > 65 and vol_breakout: 
                return "SELL", prob
        
        elif self.personality == 'STEADY':
            # 穩健派 (Trend)：要求 15 分鐘趨勢確認 (EMA200) + 7 成勝率
            ema200 = df_15m.iloc[-1].get('EMA200', current_price)
            is_uptrend = current_price > ema200
            
            if prob >= 0.75 and is_uptrend and rsi_1m < 45: 
                return "BUY", prob
            if prob <= 0.25 and not is_uptrend and rsi_1m > 55: 
                return "SELL", prob
            
        elif self.personality == 'RISK_GUARD':

            # 風控派: 監視巨鯨與恐懼貪婪，擁有否決權
            whale_score = market_context.get('whale_score', 1.0)
            if whale_score < 0.8: return "FORBID_BUY", 0 # 巨鯨在逃，禁止做多
            if whale_score > 1.2: return "FORBID_SELL", 1 # 巨鯨在買，禁止放空
            
        return "HOLD", 0.5

class ChiefAnalyst:
    """首席交易員 (組長): 負責統整專家團隊建議，具備達爾文權重系統 (根據績效調整話語權)"""
    def __init__(self, symbol, storage):
        self.symbol = symbol
        self.storage = storage
        # 組建專家團隊
        self.team = {
            'scalper': ExpertAgent("Scalper", "AGGRESSIVE", symbol, storage),
            'trend': ExpertAgent("Trend", "STEADY", symbol, storage),
            'guard': ExpertAgent("Guard", "RISK_GUARD", symbol, storage)
        }
        self.decision_log = []
        self.prestige_score = 1.0 # 初始聲望為 1.0

    def _calculate_prestige(self):
        """達爾文機制: 根據最近兩天的績效計算組長聲望"""
        try:
            perf = self.storage.get_symbol_performance(self.symbol, days=2)
            if not perf or perf.get('total_trades', 0) < 3:
                return 1.0
            
            pnl = perf.get('total_pnl', 0)
            win_rate = float(perf.get('win_rate', '50%').replace('%','')) / 100
            
            # 聲望公式: 1.0(底薪) + 績效加成 (封頂 2.0, 底限 0.5)
            # 賺錢且勝率高 -> 聲望上升；賠錢 -> 聲望降為 0.5 (觀察期)
            if pnl > 0:
                score = 1.0 + (pnl / 100) + (win_rate - 0.5)
            else:
                score = 0.5 # 進入冷靜期
                
            return max(0.5, min(2.0, score))
        except:
            return 1.0

    def make_final_decision(self, df_1m, df_15m, global_context):
        """組長拍板流程: 包含聲望與資金權重"""
        self.prestige_score = self._calculate_prestige()
        
        votes = {}
        # ... (專家投票邏輯保持不變) ...
        for name, agent in self.team.items():
            vote, confidence = agent.analyze(df_1m, df_15m, global_context)
            votes[name] = {"vote": vote, "conf": confidence}
        
        # 拍板邏輯: 組長負責制
        # 1. 檢查風控派有無否決
        if votes['guard']['vote'] == "FORBID_BUY" and (votes['scalper']['vote'] == "BUY" or votes['trend']['vote'] == "BUY"):
            self._log_decision("INTERCEPTED", "風控特工攔截了多單進場")
            return "HOLD", 0.5
        
        # 2. 如果穩健派和激進派達成共識
        if votes['scalper']['vote'] == votes['trend']['vote'] and votes['scalper']['vote'] != "HOLD":
            final_action = votes['scalper']['vote']
            avg_conf = (votes['scalper']['conf'] + votes['trend']['conf']) / 2
            self._log_decision(final_action, f"團隊共識達成: {final_action}")
            return final_action, avg_conf
            
        # 3. 檢查市場情緒 (黑科技權重)
        funding = global_context.get('funding_sentiment', 0.5)
        ls_ratio = global_context.get('ls_ratio', 0.5)
        
        # 情緒攔截邏輯: 如果資金費率極端，禁止追漲殺跌
        if funding < 0.3 and votes['scalper']['vote'] == "BUY":
            self._log_decision("HOLD", "情緒攔截: 資金費率過高，多頭擁擠禁止進場")
            return "HOLD", 0.5
        if funding > 0.7 and votes['scalper']['vote'] == "SELL":
            self._log_decision("HOLD", "情緒攔截: 資金費率過低，空頭擁擠禁止進場")
            return "HOLD", 0.5

        # 4. 如果意見分歧，組長查看全球偏向 (Global Bias) 做最後決定
        global_bias = global_context.get('global_bias', 0.5)
        if votes['scalper']['vote'] == "BUY" and global_bias > 0.6 and funding >= 0.4:
            self._log_decision("BUY", "組長依據全球偏向支持激進進場")
            return "BUY", votes['scalper']['conf']
        
        return "HOLD", 0.5

    def _log_decision(self, action, reason):
        log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {self.symbol} 組長拍板: {action} | 原因: {reason}"
        self.decision_log.append(log_entry)
        if self.storage:
            self.storage.save_global_config(f"LAST_CHIEF_DECISION_{self.symbol}", log_entry)
