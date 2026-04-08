def check_signal_scalper(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0, funding_rate=0.01, btc_change=0.0, sym_change=0.0):
    """
    【世界級趨勢突擊部隊 V3】: 引入波動率過濾與相對強度。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    
    price = last_1m['close']
    ema200 = last_15m['EMA200']
    
    # 🕵️ 1. 波動率過濾 (Volatility Gating)
    # 判斷當前 1m 波動是否超過過去 1h 平均波動的 3 倍
    current_vol = df_1m['close'].pct_change().std()
    avg_vol_1h = df_1m['close'].pct_change().rolling(60).std().mean()
    if current_vol > avg_vol_1h * 3.0:
        return "HOLD" # 市場太瘋狂，強制觀望避開插針
    
    # 🕵️ 2. 相對強度 (Relative Strength)
    # 如果是山寨幣，漲幅必須強於 BTC 才開多，反之強於 BTC 才開空
    is_stronger_than_btc = sym_change > btc_change

    macro_trend_up = True if price > ema200 else False
    bb_upper = last_15m['BB_Upper']
    bb_lower = last_15m['BB_Lower']
    
    # [多頭策略]: 趨勢向上 + 價格回踩 + 強於 BTC + AI 信心
    technical_buy = (price < bb_lower * 1.002 and last_1m['RSI'] < 40)
    if macro_trend_up and not (funding_rate > 0.04):
        confidence_threshold = 0.75 if is_stronger_than_btc else 0.85
        if (technical_buy or price > bb_upper) and ml_prob > confidence_threshold:
            return "BUY_SCALP"
            
    # [空頭策略]: 趨勢向下 + 觸頂 + 弱於 BTC + AI 信心
    technical_sell = (price > bb_upper * 0.998 and last_1m['RSI'] > 70)
    if not macro_trend_up:
        confidence_threshold = 0.2 if not is_stronger_than_btc else 0.1
        if technical_sell and ml_prob < confidence_threshold:
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
