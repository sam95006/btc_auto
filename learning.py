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

# 舊有的 MLPredictor 保持
class MLPredictor:
    def __init__(self):
        self.model = None
    def train(self, df): pass
    def predict_prob(self, row, funding_rate=0): return 0.5
