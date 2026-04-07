def check_signal(df):
    latest = df.iloc[-1]
    
    price = latest['close']
    ma20 = latest['MA20']
    rsi = latest['RSI']
    macd = latest['MACD']
    
    # 策略需求：
    # 1. 價格 > MA20 且 MACD > 0 且 RSI < 70 → BUY
    # 2. 價格 < MA20 → SELL
    
    if price > ma20 and macd > 0 and rsi < 70:
        return 'BUY'
    
    if price < ma20:
        return 'SELL'
        
    return 'HOLD'
