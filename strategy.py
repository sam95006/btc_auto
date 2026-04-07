def check_signal_scalper(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0):
    """
    【高頻突擊部隊】: 只要勝率 > 0.6，且沒有明顯崩盤風險，就進行小額試探。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    
    technical_buy = (last_1m['RSI'] < 45 and last_15m['RSI'] < 50)
    technical_sell = (last_1m['RSI'] > 65 and last_15m['RSI'] > 60)
    
    leverage_danger = True if oi_delta > 0.04 else False
    news_danger = True if news_score < 0.3 else False
    
    if not (news_danger or leverage_danger):
        if technical_buy and ml_prob > 0.6:
            return "BUY_SCALP"
            
    if technical_sell and ml_prob < 0.4:
        return "SELL_SCALP"
        
    return "HOLD"

def check_signal_sniper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, tech_pulse, fed_score, pol_score):
    """
    【極限狙擊部隊】: 必須勝率 > 0.8，且宏觀(Fed+政治)、新聞、巨鯨全部達成共振。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    technical_buy = (last_1m['RSI'] < 40 and last_15m['RSI'] < 45 and last_1h['RSI'] < 50)
    
    leverage_danger = True if oi_delta > 0.02 else False
    whale_power = True if whale_ratio > 1.3 else False
    
    # 宏觀沒有利空 (包含政治、聯準會、新聞)
    macro_safe = True if (fed_score > 0.4 and pol_score > 0.4 and news_score > 0.4) else False
    tech_boost = True if tech_pulse > 1.1 else False

    if not leverage_danger and macro_safe:
        # 當機器學習勝率極高，且巨鯨進場、美股助攻時，火力全開
        if ml_prob > 0.8 and whale_power and tech_boost and technical_buy:
            return "SUPER_BUY"
    
    return "HOLD"
