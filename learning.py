import numpy as np

class ReflectionEngine:
    def __init__(self, storage):
        self.storage = storage

    def analyze_loss(self, symbol, pnl, entry_price, exit_price, direction, market_context):
        """
        深度分析與反思虧損原因。
        market_context: 包含 {'rsi':, 'ema200':, 'atr':, 'ml_prob':, 'volatility':}
        """
        if pnl >= 0:
            return "✅ 本次交易獲利，維持當前策略節奏。"

        # 核心反思邏輯
        reasons = []
        
        # 1. 檢查止損寬度
        if market_context.get('volatility', 0) > market_context.get('atr', 0) * 1.5:
            reasons.append("⚠️ 市場波動劇烈，ATR 空間設太窄，導致被隨機雜訊掃出場。")
            
        # 2. 檢查趨勢一致性
        price = exit_price
        ema = market_context.get('ema200', price)
        if direction == "LONG" and price < ema:
            reasons.append("❌ 在趨勢線 (EMA200) 下方強行做多，屬於逆勢操作陷阱。")
        elif direction == "SHORT" and price > ema:
            reasons.append("❌ 在趨勢線 (EMA200) 上方強行做空，被軋空風險極高。")
            
        # 3. 檢查 AI 信心
        if market_context.get('ml_prob', 0) < 0.7:
            reasons.append("🩹 AI 信心值僅為邊緣區，過度頻繁交易弱訊號導致虧損。")

        reason_str = " | ".join(reasons) if reasons else "🌀 市場極端異常波動，非技術性指標可判定。"
        
        # 將心得寫入資料庫
        context_str = str(market_context)
        self.storage.log_lesson(symbol, pnl, reason_str, context_str)
        
        return f"💡 【深度反思報表】\n{reason_str}\n♻️ 已將此經驗存入資料庫，下次遇到相似情境將自動預警。"

# 舊有的 MLPredictor 保持
class MLPredictor:
    def __init__(self):
        self.model = None
    def train(self, df): pass
    def predict_prob(self, row, funding_rate=0): return 0.5
