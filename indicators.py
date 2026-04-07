import pandas as pd
import numpy as np

def calculate_all(df):
    # 1. MA20 (均線)
    df['MA20'] = df['close'].rolling(window=20).mean()
    
    # 2. RSI (相對強弱)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 3. MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # 4. Bollinger Bands (布林帶 - 極限過濾)
    df['STD'] = df['close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['STD'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['STD'] * 2)
    
    # 5. Relative Volume (相對成交量 - 巨鯨監控)
    # 如果目前成交量 > 過去20根平均的 2.0 倍，代表巨鯨在動作
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
    df['RV'] = df['volume'] / df['Vol_MA20']
    
    return df
