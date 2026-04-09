def check_signal_scalper(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0, funding_rate=0.01, btc_change=0.0, sym_change=0.0, market_regime=None, optimized_params=None):
    """
    【世界級趨勢突擊部隊 V4】: 引入市場制度感知 + 自學習參數。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    
    price = last_1m['close']
    ema200 = last_15m['EMA200']
    
    # 使用自學習參數或預設值
    if optimized_params:
        rsi_buy_low = optimized_params.get('rsi_buy_low', 30)
        rsi_sell_high = optimized_params.get('rsi_sell_high', 70)
        bb_std_dev = optimized_params.get('bb_std_dev', 2.0)
    else:
        rsi_buy_low = 30
        rsi_sell_high = 70
        bb_std_dev = 2.0
    
    # 🕵️ 1. 波動率過濾 (Volatility Gating)
    current_vol = df_1m['close'].pct_change().std()
    avg_vol_1h = df_1m['close'].pct_change().rolling(60).std().mean()
    if current_vol > avg_vol_1h * 3.0:
        return "HOLD"  # 市場太瘋狂
    
    # 🕵️ 2. 市場制度過濾
    if market_regime:
        regime_name = market_regime.get('regime', 'RANGING')
        
        # 高波動市場: 降低交易頻率
        if regime_name == 'HIGH_VOLATILITY':
            if ml_prob < 0.92:  # 只有超高信心才進場
                return "HOLD"
        
        # 強下降趨勢: 避免做多
        elif regime_name == 'STRONG_DOWNTREND':
            return "HOLD"  # 等待反轉信號
    
    # 🕵️ 3. 相對強度 (Relative Strength)
    is_stronger_than_btc = sym_change > btc_change

    macro_trend_up = True if price > ema200 else False
    bb_upper = last_15m['BB_Upper']
    bb_lower = last_15m['BB_Lower']
    
    # [多頭策略]: 趨勢向上 + 價格回踩 + 強於 BTC + AI 信心
    technical_buy = (price < bb_lower * 1.002 and last_1m['RSI'] < rsi_buy_low)
    if macro_trend_up and not (funding_rate > 0.04):
        confidence_threshold = 0.75 if is_stronger_than_btc else 0.85
        if (technical_buy or price > bb_upper) and ml_prob > confidence_threshold:
            return "BUY_SCALP"
            
    # [空頭策略]: 趨勢向下 + 觸頂 + 弱於 BTC + AI 信心
    technical_sell = (price > bb_upper * 0.998 and last_1m['RSI'] > rsi_sell_high)
    if not macro_trend_up:
        confidence_threshold = 0.2 if not is_stronger_than_btc else 0.1
        if technical_sell and ml_prob < confidence_threshold:
            return "SELL_SCALP"
        
    return "HOLD"

def check_signal_sniper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, tech_pulse, fed_score, pol_score, funding_rate=0.01, market_regime=None, optimized_params=None):
    """
    【極限趨勢狙擊手 V3】: 結合 EMA200、昨日低點、市場制度、自學習參數。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    
    price = last_1m['close']
    ema200 = last_15m['EMA200']
    daily_low = last_1m['DailyLow']
    
    # 使用自學習參數
    if optimized_params:
        atr_stop_loss = optimized_params.get('atr_stop_loss', 1.5)
    else:
        atr_stop_loss = 1.5
    
    # 市場制度判定
    regime_name = market_regime.get('regime', 'RANGING') if market_regime else 'RANGING'
    
    # 弱趨勢或高波動: 不進場狙擊
    if regime_name in ['WEAK_UPTREND', 'HIGH_VOLATILITY', 'RANGING']:
        return "HOLD"
    
    # 狙擊手原則 1：只在回調至強支撐 (EMA200 或 昨日低位) 且趨勢向上時進場
    on_support = True if (price - daily_low)/daily_low < 0.005 or (abs(price - ema200)/ema200 < 0.005) else False
    
    macro_bullish = True if (fed_score > 0.55 and news_score > 0.55) else False
    
    if price > ema200 and macro_bullish and regime_name in ['UPTREND', 'STRONG_UPTREND']:
        # 強大共振：回踩支撑 + 巨鯨強勢掃貨 + AI 極高機率 + 強上升趨勢
        if ml_prob > 0.82 and whale_ratio > 1.3 and on_support:
            return "SUPER_BUY"
            
    return "HOLD"

def get_support_resistance_levels(df_1h, period=20):
    """
    【自動支撐阻力識別】
    辨識過去 N 根 1h K 線的支撐和阻力位
    """
    if len(df_1h) < period:
        return {}, {}
    
    recent = df_1h.tail(period)
    
    # 支撐: 過去 N 根 K 線的最低低點
    support_level = recent['low'].min()
    resistance_level = recent['high'].max()
    
    # 次要支撐/阻力
    sorted_lows = recent['low'].nlargest(3).values
    sorted_highs = recent['high'].nsmallest(3).values
    
    support_zone = {
        'primary': support_level,
        'secondary': sorted_lows[1] if len(sorted_lows) > 1 else support_level
    }
    
    resistance_zone = {
        'primary': resistance_level,
        'secondary': sorted_highs[1] if len(sorted_highs) > 1 else resistance_level
    }
    
    return support_zone, resistance_zone
