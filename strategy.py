def check_signal(df_1m, df_15m, df_1h):
    if len(df_1m) < 20 or len(df_1h) < 20:
        return "NEUTRAL"
    
    # --- 大趨勢過濾 (1h 指南針) ---
    latest_1h = df_1h.iloc[-1]
    # 如果大週期價格低於均線，視為大勢看空
    is_major_bull = latest_1h['close'] > latest_1h['MA20']
    is_major_bear = latest_1h['close'] < latest_1h['MA20']

    # --- 中週期判定 (15m 波段) ---
    latest_15m = df_15m.iloc[-1]
    is_minor_bull = latest_15m['close'] > latest_15m['MA20']

    # --- 1m 精準狙擊訊號 ---
    latest_1m = df_1m.iloc[-1]
    prev_1m = df_1m.iloc[-2]

    # ✅ 高勝率買入 (Long) 條件：大趨勢向上 + 小週期超跌反彈 + 巨鯨增量
    long_condition = (
        is_major_bull and 
        latest_1m['close'] < latest_1m['Lower_Band'] * 1.002 and  # 小週期超跌
        latest_1m['RV'] > 1.3 and                                 # 巨鯨增量
        latest_1m['MACD'] > prev_1m['MACD']                       # 動能轉強
    )

    # ✅ 高勝率放空 (Short) 條件：大趨勢向下 + 小週期超漲 + 巨鯨撤出
    short_condition = (
        is_major_bear and
        latest_1m['close'] > latest_1m['Upper_Band'] * 0.998 and # 小週期超漲
        latest_1m['RV'] > 1.3 and                                # 巨鯨出貨
        latest_1m['MACD'] < prev_1m['MACD']                     # 動能轉弱
    )

    if long_condition:
        return "BUY"
    elif short_condition:
        return "SELL"
    else:
        return "NEUTRAL"
