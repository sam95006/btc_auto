import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import numpy as np

class MLPredictor:
    def __init__(self):
        # 初始化隨機森林模型：平衡快速訓練與準確度
        self.model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        self.is_trained = False

    def train(self, df):
        """
        利用過去的 K 線數據與後續漲跌進行「自我學習」
        """
        if len(df) < 100:
            return False
        
        # 標記：如果未來 5 根 K 線內漲超過 0.5% 則標記為成功 (1), 否則為 0
        df['target'] = (df['close'].shift(-5) > df['close'] * 1.005).astype(int)
        
        # 特徵工程：使用我們最強的指標作為輸入
        features = ['RSI', 'MACD', 'RV', 'STD']
        X = df[features].iloc[:-5].dropna()
        y = df['target'].loc[X.index]
        
        if len(X) > 50:
            self.model.fit(X, y)
            self.is_trained = True
            print("AI 大腦訓練完成: 已學習最新市場動態。")
            return True
        return False

    def predict_prob(self, latest_data):
        """
        預測當前訊號成功的機率
        """
        if not self.is_trained:
            return 0.5  # 未訓練前預設中立
        
        features = ['RSI', 'MACD', 'RV', 'STD']
        X_test = pd.DataFrame([latest_data[features]])
        prob = self.model.predict_proba(X_test)[0][1]
        return prob
