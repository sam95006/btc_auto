def check_signal(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0):
    # 【超精準：五位一體決策矩陣】
    # 技術 + AI + 巨鯨 + 新聞 + 槓桿壓力(OI)
    
    # 1. 基礎技術指標 (1m, 15m, 1h 三重共振)
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    technical_buy = (last_1m['RSI'] < 40 and last_15m['RSI'] < 45 and last_1h['RSI'] < 50)
    technical_sell = (last_1m['RSI'] > 70 and last_15m['RSI'] > 65 and last_1h['RSI'] > 60)
    
    # 2. 槓桿壓力計 (Open Interest Delta)
    # 如果 OI 短時間暴漲超過 3%，通常是瘋狂槓桿追單，預示著即將到來的「血洗爆倉」。
    leverage_danger = True if oi_delta > 0.03 else False
    leverage_squeeze = True if (oi_delta < -0.05 and last_1m['close'] > last_1m['open']) else False
    
    # 3. 巨鯨力場 & 新聞情緒
    whale_power = True if whale_ratio > 1.3 else False
    news_danger = True if news_score < 0.3 else False
    
    # 🚨 【終極買入判定】 (過濾槓桿陷阱)
    if not (news_danger or leverage_danger):
        # 正常共振買入 OR (空頭爆倉導致的強力擠壓訊號)
        if (technical_buy and ml_prob > 0.6) or (leverage_squeeze and ml_prob > 0.7):
            return "BUY"
    
    # 🚨 【終極賣出判定】 (抓取槓桿崩潰)
    if (technical_sell and ml_prob < 0.4) or (ml_prob < 0.15 and whale_ratio < 0.7) or (news_score < 0.2):
        return "SELL"
    
    return "HOLD"
