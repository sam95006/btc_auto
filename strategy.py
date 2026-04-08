def check_signal_scalper(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0):
    """
    【高頻突擊部隊】: 優化版 - 增加趨勢過濾，防止在強漲勢中逆勢做空。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    # 趨勢判定：如果 1小時 RSI > 55，代表大趨勢向上，禁止做空
    trend_up = True if last_1h['RSI'] > 55 else False
    
    technical_buy = (last_1m['RSI'] < 45 and last_15m['RSI'] < 50)
    # 做空條件更嚴格：RSI 要極高且大趨勢不能向上
    technical_sell = (last_1m['RSI'] > 75 and last_15m['RSI'] > 70 and not trend_up)
    
    leverage_danger = True if oi_delta > 0.04 else False
    news_danger = True if news_score < 0.3 else False
    
    if not (news_danger or leverage_danger):
        if technical_buy and ml_prob > 0.65:
            return "BUY_SCALP"
            
    # 做空信心門檻從 0.4 下修到 0.2 (代表 AI 判定極度看空才做)
    if technical_sell and ml_prob < 0.2:
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
