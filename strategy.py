def check_signal_scalper(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0, funding_rate=0.01):
    """
    【世界級趨勢突擊部隊 V2】: 基於 EMA200 生命線與布林帶能量。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    price = last_1m['close']
    ema200 = last_15m['EMA200'] # 使用 15 分鐘線作為主要趨勢生命線
    
    # 💎 核心趨勢過濾：價格在 EMA200 以上 = 只允許多單；以下 = 只允許空單
    macro_trend_up = True if price > ema200 else False
    
    # 布林帶能量
    bb_upper = last_15m['BB_Upper']
    bb_lower = last_15m['BB_Lower']
    
    # [多頭策略]: 趨勢向上 + 價格回踩布林帶下軌點火彈起 + AI信心強
    technical_buy = (price < bb_lower * 1.002 and last_1m['RSI'] < 40)
    if macro_trend_up and not (funding_rate > 0.04):
        # AI 勝率門檻大幅提高到 0.75，只做高品質的單
        if (technical_buy or price > bb_upper) and ml_prob > 0.75:
            return "BUY_SCALP"
            
    # [空頭策略]: 趨勢向下 + 價格觸碰布林頂軌受阻 + AI信心極強
    technical_sell = (price > bb_upper * 0.998 and last_1m['RSI'] > 70)
    if not macro_trend_up:
        if technical_sell and ml_prob < 0.2:
            return "SELL_SCALP"
        
    return "HOLD"

def check_signal_sniper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, tech_pulse, fed_score, pol_score, funding_rate=0.01):
    """
    【極限趨勢狙擊手 V2】: 結合 EMA200、昨日低點與總體經濟共振。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    
    price = last_1m['close']
    ema200 = last_15m['EMA200']
    daily_low = last_1m['DailyLow']
    
    # 狙擊手原則 1：只在回調至強支撐 (EMA200 或 昨日低位) 且趨勢向上時進場
    on_support = True if (price - daily_low)/daily_low < 0.005 or (abs(price - ema200)/ema200 < 0.005) else False
    
    macro_bullish = True if (fed_score > 0.55 and news_score > 0.55) else False
    
    if price > ema200 and macro_bullish:
        # 強大共振：回踩支撐 + 巨鯨強勢掃貨 + AI 極高機率
        if ml_prob > 0.82 and whale_ratio > 1.3 and on_support:
            return "SUPER_BUY"
            
    return "HOLD"
