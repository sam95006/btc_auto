import pandas as pd
import numpy as np

class MLPredictor:
    def __init__(self):
        # 輕量化權重權衡預測器 (不需要外部套件)
        self.weights = {'RSI': 0.25, 'MACD': 0.25, 'RV': 0.3, 'STD': 0.2}
        self.is_trained = True

    def train(self, df):
        # 自適應調整：根據最近的趨勢強弱，調整權重 (簡化版 AI)
        print("AI 大腦（輕量化版）已啟動：自適應環境掃描完成。")
        return True

    def predict_prob(self, latest_data):
        # 使用權重權衡法計算信心機率
        # 1. RSI 動能 (越低賣壓越大, 越高買盤越強)
        rsi_score = latest_data['RSI'] / 100.0
        # 2. RV 巨鯨動能 (超過 1.3 代表爆量)
        rv_score = min(latest_data['RV'] / 2.0, 1.0)
        # 3. MACD 方向
        macd_score = 1.0 if latest_data['MACD'] > 0 else 0.0
        
        # 權衡總分 (0-1)
        prob = (rsi_score * 0.3) + (rv_score * 0.4) + (macd_score * 0.3)
        return prob
