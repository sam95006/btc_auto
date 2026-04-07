import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from strategy import calculate_rsi, calculate_sma

class MLPredictor:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.is_trained = False

    def prepare_features(self, df):
        # Create features
        df = df.copy()
        df['rsi'] = calculate_rsi(df)
        df['sma_20'] = calculate_sma(df, 20)
        df['sma_50'] = calculate_sma(df, 50)
        df['price_change'] = df['close'].pct_change()
        
        # Target: 1 if price goes UP in next 5 periods, 0 otherwise
        df['target'] = (df['close'].shift(-5) > df['close']).astype(int)
        
        # Clean data
        df = df.dropna()
        X = df[['rsi', 'sma_20', 'sma_50', 'price_change']]
        y = df['target']
        return X, y

    def train(self, df):
        if len(df) < 100:
            print("Not enough data to train ML model yet (need >100 rows).")
            return
            
        X, y = self.prepare_features(df)
        self.model.fit(X, y)
        self.is_trained = True
        print(f"ML Model trained on {len(df)} rows.")

    def predict_signal(self, current_df):
        if not self.is_trained:
            return None # Fallback to standard strategy

        X, _ = self.prepare_features(current_df)
        if len(X) == 0: return None
        
        last_features = X.iloc[-1].values.reshape(1, -1)
        prob = self.model.predict_proba(last_features)[0][1] # Probability of UP
        
        print(f"ML Confidence: {prob:.2f}")
        
        if prob > 0.7: return 'BUY'
        if prob < 0.3: return 'SELL'
        return 'HOLD'
