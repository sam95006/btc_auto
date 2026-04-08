def check_signal_scalper(df_1m, df_15m, df_1h, ml_prob=0.5, whale_ratio=1.0, news_score=0.5, oi_delta=0.0, funding_rate=0.01):
    """
    【高頻突擊部隊】: 增加支撐壓力支撐與資金費率偵測。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    # 趨勢與關鍵位判定
    rsi_h = last_1h['RSI']
    trend_up = True if rsi_h > 55 else False
    
    # 🔑 加入昨日高低點意識
    daily_high = last_1m['DailyHigh']
    daily_low = last_1m['DailyLow']
    curr_price = last_1m['close']
    
    # [資金費率陷阱]: 如果 FR > 0.04% 代表多頭過熱，禁止追多
    funding_danger = True if funding_rate > 0.04 else False
    
    # [做多過濾]: 不在昨日高點附近追多，除非強勢突破
    near_resistance = True if (daily_high - curr_price) / curr_price < 0.005 else False
    
    technical_buy = (last_1m['RSI'] < 45 and last_15m['RSI'] < 50)
    # 做多條件：AI看多 + 不是高位追漲 + 費率安全
    if not funding_danger and not (near_resistance and rsi_h > 65):
        if technical_buy and ml_prob > 0.65:
            return "BUY_SCALP"
            
    # [做空條件]: AI極度看空 + 大趨勢向下 + RSI極高
    technical_sell = (last_1m['RSI'] > 75 and last_15m['RSI'] > 70 and not trend_up)
    if technical_sell and ml_prob < 0.2:
        return "SELL_SCALP"
        
    return "HOLD"

def check_signal_sniper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, tech_pulse, fed_score, pol_score, funding_rate=0.01):
    """
    【極限狙擊部隊】: 加入宏觀、費率與關鍵點位共振。
    """
    last_1m = df_1m.iloc[-1]
    last_15m = df_15m.iloc[-1]
    last_1h = df_1h.iloc[-1]
    
    curr_price = last_1m['close']
    daily_low = last_1m['DailyLow']
    
    # 狙擊手專屬條件：在「昨日低點」附近且 AI 信心爆表
    near_support = True if (curr_price - daily_low) / daily_low < 0.008 else False
    
    technical_buy = (last_1m['RSI'] < 40 and last_15m['RSI'] < 45 and last_1h['RSI'] < 50)
    macro_safe = True if (fed_score > 0.5 and pol_score > 0.5 and news_score > 0.5) else False
    
    # [資金費率檢查] 狙擊手絕不參與多頭派對末端
    if funding_rate < 0.03 and macro_safe:
        # 特別條件：如果是在強支撐區 (昨日低位) + AI > 0.8 + 巨鯨進場 = 全力開火
        if ml_prob > 0.8 and whale_ratio > 1.2 and near_support:
            return "SUPER_BUY"
            
    return "HOLD"
