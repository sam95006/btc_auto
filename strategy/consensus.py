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
        """專家根據自己的性格給出建議"""
        prob = self.predictor.predict_prob(df_1m.iloc[-1], market_context=market_context)
        
        if self.personality == 'AGGRESSIVE':
            # 激進派: 只要有一點點突破就想進場
            if prob > 0.65: return "BUY", prob
            if prob < 0.35: return "SELL", prob
        
        elif self.personality == 'STEADY':
            # 穩健派: 要求趨勢確認 (EMA200) 與較高信心
            ema200 = df_15m.iloc[-1].get('EMA200', df_1m.iloc[-1]['close'])
            is_uptrend = df_1m.iloc[-1]['close'] > ema200
            if prob > 0.8 and is_uptrend: return "BUY", prob
            if prob < 0.2 and not is_uptrend: return "SELL", prob
            
        elif self.personality == 'RISK_GUARD':
            # 風控派: 監視巨鯨與恐懼貪婪，擁有否決權
            whale_score = market_context.get('whale_score', 1.0)
            if whale_score < 0.8: return "FORBID_BUY", 0 # 巨鯨在逃，禁止做多
            if whale_score > 1.2: return "FORBID_SELL", 1 # 巨鯨在買，禁止放空
            
        return "HOLD", 0.5

class ChiefAnalyst:
    """首席交易員 (組長): 負責統整專家團隊建議並拍板下單"""
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

    def make_final_decision(self, df_1m, df_15m, global_context):
        """組長拍板流程"""
        votes = {}
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
            
        # 3. 如果意見分歧，組長查看全球偏向 (Global Bias) 做最後決定
        global_bias = global_context.get('global_bias', 0.5)
        if votes['scalper']['vote'] == "BUY" and global_bias > 0.6:
            self._log_decision("BUY", "組長依據全球偏向支持激進進場")
            return "BUY", votes['scalper']['conf']
            
        return "HOLD", 0.5

    def _log_decision(self, action, reason):
        log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {self.symbol} 組長拍板: {action} | 原因: {reason}"
        self.decision_log.append(log_entry)
        if self.storage:
            self.storage.save_global_config(f"LAST_CHIEF_DECISION_{self.symbol}", log_entry)
