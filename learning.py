import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

class MLPredictor:
    def __init__(self):
        # 建立專業級隨機森林模型
        self.model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        self.is_trained = False

    def train(self, df):
        try:
            # 準備訓練數據
            # 特徵 (Features): RSI, MACD, RV, ATR, etc.
            X = df[['RSI', 'MACD', 'RV']].values
            
            # 目標 (Label): 如果下一根收盤價是漲的 ( > 0)，則標記為 1 (買入信心)
            y = (df['close'].shift(-1) > df['close']).astype(int).values
            
            # 移除最後一行 (因為沒有下一根價格可對照)
            X = X[:-1]
            y = y[:-1]
            
            if len(X) > 50:
                self.model.fit(X, y)
                self.is_trained = True
                print(f"✅ AI 專業大腦訓練完成。樣本數: {len(X)}")
        except Exception as e:
            print(f"❌ AI 訓練發生錯誤: {e}")

    def predict_prob(self, latest_data):
        if not self.is_trained:
            return 0.5
        
        try:
            features = np.array([[latest_data['RSI'], latest_data['MACD'], latest_data['RV']]])
            # 取得「看漲」的機率
            probs = self.model.predict_proba(features)
            return probs[0][1] # 返回 Index 1 (即標籤為 1, 漲的機率)
        except:
            return 0.5
