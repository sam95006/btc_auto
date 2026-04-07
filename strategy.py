def check_signal(df_1m, df_15m, df_1h, ml_prob=0.5):
    if len(df_1m) < 20 or len(df_1h) < 20:
        return "NEUTRAL"
    
    # --- 大趨勢過濾 (1h 指南針) ---
    latest_1h = df_1h.iloc[-1]
    is_major_bull = latest_1h['close'] > latest_1h['MA20']
    is_major_bear = latest_1h['close'] < latest_1h['MA20']

    # --- 1m 精準狙擊訊號 (原有指標) ---
    latest_1m = df_1m.iloc[-1]
    prev_1m = df_1m.iloc[-2]

    # --- 🧠 AI 信心過濾條件 (自適應判定) ---
    # 如果 AI 判定成功機率不足 60%，代表目前波動太隨機，拒絕交易
    ai_confidence = ml_prob > 0.60
    ai_short_conf = ml_prob < 0.40  # 越低代表跌勢越穩

    # ✅ 高勝率買入 (Long) 條件：大趨勢向上 + 小週期超跌反彈 + 巨鯨增量 + AI信心
    long_condition = (
        is_major_bull and 
        latest_1m['close'] < latest_1m['Lower_Band'] * 1.002 and
        latest_1m['RV'] > 1.3 and
        latest_1m['MACD'] > prev_1m['MACD'] and
        ai_confidence
    )

    # ✅ 高勝率放空 (Short) 條件：大趨勢向下 + 小週期超漲 + 巨鯨撤出 + AI信心
    short_condition = (
        is_major_bear and
        latest_1m['close'] > latest_1m['Upper_Band'] * 0.998 and
        latest_1m['RV'] > 1.3 and
        latest_1m['MACD'] < prev_1m['MACD'] and
        ai_short_conf
    )

    if long_condition:
        return "BUY"
    elif short_condition:
        return "SELL"
    else:
        return "NEUTRAL"
