import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

class MLPredictor:
    def __init__(self):
        # 增加決策樹深度，讓它能理解更複雜的「指標+情緒」組合
        self.model = RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42)
        self.is_trained = False

    def train(self, df):
        try:
            # 加入波動率特徵 (ATR)
            X = df[['RSI', 'MACD', 'RV', 'ATR']].values
            
            # y 標籤：收盤漲跌
            y = (df['close'].shift(-1) > df['close']).astype(int).values
            
            X = X[:-1]
            y = y[:-1]
            
            if len(X) > 50:
                self.model.fit(X, y)
                self.is_trained = True
                print(f"✅ 企業級 AI 決策核心升級完成。樣本數: {len(X)}")
        except Exception as e:
            print(f"❌ AI 訓練發生錯誤: {e}")

    def predict_prob(self, latest_data, funding_rate=0.0):
        if not self.is_trained:
            return 0.5
        
        try:
            # 偵測最新特徵
            features = np.array([[latest_data['RSI'], latest_data['MACD'], latest_data['RV'], latest_data['ATR']]])
            probs = self.model.predict_proba(features)
            raw_prob = probs[0][1]
            
            # --- 情緒修正模組 (Sentiment Overlay) ---
            # 如果全網都在做多 (Funding Rate 高)，則看漲的「安全性機率」會被扣分
            # 如果全網都在割空 (Funding Rate 負)，則看漲的「潛在機率」會加分
            sentiment_adjust = - (funding_rate * 2) # 將費率放大倍數進行修正
            final_prob = np.clip(raw_prob + sentiment_adjust, 0.0, 1.0)
            
            return final_prob
        except:
            return 0.5
