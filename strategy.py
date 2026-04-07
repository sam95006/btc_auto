def check_signal(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0, tech_pulse=1.0):
    # 【神級：六位一體進化矩陣】
    # 技術 + AI + 巨鯨 + 新聞 + 槓桿 + 美股科技連動
    
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    technical_buy = (last_1m['RSI'] < 40 and last_15m['RSI'] < 45 and last_1h['RSI'] < 50)
    
    leverage_danger = True if oi_delta > 0.03 else False
    whale_power = True if whale_ratio > 1.3 else False
    news_danger = True if news_score < 0.3 else False
    
    # 💡 [美股科技助攻]：當 NVDA 情緒高昂，BTC 的韌性會變強
    tech_boost = True if tech_pulse > 1.15 else False

    # 🚨 【決策下達】
    if not (news_danger or leverage_danger):
        # 1. 極致訊號 (Super Buy)：多重指標共振且美股力挺
        if ml_prob > 0.9 and whale_power and tech_boost:
            return "SUPER_BUY"
            
        # 2. 標準訊號
        if (technical_buy and ml_prob > 0.6) or (ml_prob > 0.8 and whale_power):
            return "BUY"
    
    # 3. 賣出判定 (維持原本邏輯)
    if (ml_prob < 0.15 and whale_ratio < 0.7) or (news_score < 0.2):
        return "SELL"
    
    return "HOLD"
