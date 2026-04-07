def check_signal(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5):
    # 【四位一體：終極決策矩陣】
    # 技術共振 + AI精算 + 巨鯨掛單 + 即時新聞情緒
    
    # 1. 基礎技術指標 (1m, 15m, 1h 三重共振)
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    technical_buy = (last_1m['RSI'] < 40 and last_15m['RSI'] < 45 and last_1h['RSI'] < 50)
    technical_sell = (last_1m['RSI'] > 70 and last_15m['RSI'] > 65 and last_1h['RSI'] > 60)
    
    # 2. 巨鯨力場偵測 (買賣盤掛單比)
    whale_power = True if whale_ratio > 1.3 else False
    
    # 3. 新聞過濾器 (當新聞非常負面時，禁止買入)
    news_danger = True if news_score < 0.3 else False
    news_boost = True if news_score > 0.7 else False
    
    # 🚨 【終極買入判定】
    # 邏輯：技術超賣 + AI 信心高位 + 無新聞警報
    if not news_danger:
        if (technical_buy and ml_prob > 0.6) or (ml_prob > 0.85 and whale_power) or (ml_prob > 0.7 and news_boost):
            return "BUY"
    
    # 🚨 【終極賣出判定】
    # 邏輯：技術超買 + AI 看跌中位 + (若是新聞暴跌則直接判斷)
    if (technical_sell and ml_prob < 0.4) or (ml_prob < 0.15 and whale_ratio < 0.7) or (news_score < 0.2):
        return "SELL"
    
    return "HOLD"
