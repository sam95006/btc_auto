def check_signal(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, macro_signal=0.5):
    # 乙太網、巨鯨、宏觀、技術綜合決策 (Fusion Decision)
    
    # 1. 基礎技術指標 (1m, 15m, 1h 三重共振)
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    technical_buy = (last_1m['RSI'] < 40 and last_15m['RSI'] < 45 and last_1h['RSI'] < 50)
    technical_sell = (last_1m['RSI'] > 70 and last_15m['RSI'] > 65 and last_1h['RSI'] > 60)
    
    # 2. 巨鯨力場偵測 (Whale Gravity)
    whale_power = True if whale_ratio > 1.3 else False # 買盤是賣盤的 1.3 倍以上
    
    # 🚨 【終極買入決策】
    # 條件：技術共振超賣 OR (AI 信心極高 + 巨鯨撐腰 + 宏觀穩定)
    if (technical_buy and ml_prob > 0.6) or (ml_prob > 0.85 and whale_power):
        return "BUY"
    
    # 🚨 【終極賣出決策】
    # 條件：技術共振超買 OR (AI 看跌信心極高 + 巨鯨逃跑 + 宏觀轉弱)
    if (technical_sell and ml_prob < 0.4) or (ml_prob < 0.15 and whale_ratio < 0.7):
        return "SELL"
    
    return "HOLD"
