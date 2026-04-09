import json
from datetime import datetime, timedelta
from collections import defaultdict

class ReflectionEngine:
    def __init__(self, storage):
        self.storage = storage

    def is_similar_to_failed_trade(self, symbol, current_context):
        """
        [自我反思決策機制]: 檢查當前環境是否與過去失敗的交易高度相似。
        """
        failed_lessons = self.storage.get_recent_lessons(symbol, limit=10)
        for lesson in failed_lessons:
            # 獲取過去失敗時的上下文 (簡化版相似度比對)
            old_ctx = eval(lesson[4]) if isinstance(lesson[4], str) else {}
            
            # 如果 RSI、波動率、以及 EMA 偏離程度與上次虧損時相似 (誤差 10% 內)
            if abs(current_context.get('rsi', 50) - old_ctx.get('rsi', 50)) < 5 and \
               abs(current_context.get('ml_prob', 0.5) - old_ctx.get('ml_prob', 0.5)) < 0.05:
                return True, lesson[3] # 判定為危險相似區
        return False, ""

    def analyze_loss(self, symbol, pnl, entry_price, exit_price, direction, market_context):
        if pnl >= 0: return ""
        reasons = []
        if market_context.get('volatility', 0) > market_context.get('atr', 0) * 1.5:
            reasons.append("⚠️ 市場波動劇烈，ATR 空間過窄。")
        price = exit_price
        ema = market_context.get('ema200', price)
        if direction == "LONG" and price < ema:
            reasons.append("❌ 在趨勢線 (EMA200) 下方強行做多。")
        elif direction == "SHORT" and price > ema:
            reasons.append("❌ 在趨勢線 (EMA200) 上方強行做空。")
        if market_context.get('ml_prob', 0) < 0.7:
            reasons.append("🩹 AI 信心值過低導致弱訊號虧損。")
        reason_str = " | ".join(reasons) if reasons else "🌀 市場極端異常波動。"
        self.storage.log_trade(f"REFLECT_{symbol}", exit_price, 0, pnl, 0)
        return f"\n💡 【深度反思報表】\n{reason_str}"

class AdaptiveMLPredictor:
    """自適應機器學習預測器 - 能自我優化"""
    def __init__(self, storage=None):
        self.model = None
        self.storage = storage
        self.param_history = defaultdict(list)  # 記錄參數歷史
        self.best_params = {
            'rsi_buylow': 30,
            'rsi_sellhigh': 70,
            'bb_sensitivity': 1.5,
            'ema_fast': 50,
            'ema_slow': 200,
            'volume_multiplier': 1.5
        }
        self.learning_rate = 0.01
        self.min_confidence = 0.60
    
    def train(self, df): 
        pass  # 使用自適應參數而不是傳統訓練
    
    def predict_prob(self, row, funding_rate=0, market_context=None):
        """基於自學習參數的預測"""
        rsi = row.get('RSI', 50)
        close = row.get('close', 0)
        ema200 = row.get('EMA200', close)
        
        # 自學習的參數
        buy_signal = rsi < self.best_params['rsi_buylow']
        sell_signal = rsi > self.best_params['rsi_sellhigh']
        in_uptrend = close > ema200
        
        # 綜合評分
        probability = 0.5
        
        if buy_signal and in_uptrend:
            probability = 0.75 + (0.25 * (1 - rsi / 30))  # 越超賣越強
        elif sell_signal and not in_uptrend:
            probability = 0.25 - (0.25 * (rsi / 100))
        
        # 資金費率調整
        if funding_rate > 0.0001:
            probability -= 0.1  # 資金費率過高，降低多頭信心
        
        return min(max(probability, 0), 1)
    
    def feedback_trade_result(self, signal_type, pnl, market_context):
        """接收交易結果反饋，持續優化參數"""
        if pnl >= 0:
            # 盈利交易：強化當前參數
            self._reinforce_params(market_context, pnl)
        else:
            # 虧損交易：調整參數
            self._adjust_params(market_context, pnl)
    
    def _reinforce_params(self, context, pnl):
        """強化成功的參數"""
        rsi = context.get('rsi', 50)
        volatility = context.get('volatility', 0)
        
        # 如果是低 RSI 買入成功，調整買入閾值
        if rsi < 40:
            self.best_params['rsi_buylow'] = max(25, self.best_params['rsi_buylow'] - 0.5)
        
        # 記錄歷史
        self.param_history['winning_params'].append({
            'timestamp': datetime.now(),
            'params': self.best_params.copy(),
            'pnl': pnl
        })
    
    def _adjust_params(self, context, pnl):
        """調整失敗的參數"""
        rsi = context.get('rsi', 50)
        
        # 如果是低 RSI 買入失敗，提高買入閾值
        if rsi < 40:
            self.best_params['rsi_buylow'] = min(45, self.best_params['rsi_buylow'] + 1)
        
        # 記錄歷史
        self.param_history['losing_params'].append({
            'timestamp': datetime.now(),
            'params': self.best_params.copy(),
            'pnl': pnl
        })
    
    def get_current_params(self):
        """返回當前優化的參數"""
        return self.best_params.copy()

class MLPredictor:
    """向後相容的 MLPredictor"""
    def __init__(self):
        self.model = None
    def train(self, df): pass
    def predict_prob(self, row, funding_rate=0): return 0.5
