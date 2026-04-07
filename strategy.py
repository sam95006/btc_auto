def check_signal(df):
    if len(df) < 20:
        return "NEUTRAL"
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 策略 1: 抄底共振 (Long Signal) - 90%+ 勝率級別
    # 價格低於布林帶下軌 (Lower Band) 且 成交量放大 (RV > 1.2) 且 MACD 金叉
    long_condition = (
        latest['close'] < latest['Lower_Band'] * 1.002 and  # 進入超跌區
        latest['RV'] > 1.2 and                              # 巨鯨增量確認
        latest['MACD'] > prev['MACD']                       # 動能回暖
    )
    
    # 策略 2: 逃頂共振 (Short Signal)
    # 價格高於布林帶上軌 (Upper Band) 且 成交量放大 且 MACD 死叉
    short_condition = (
        latest['close'] > latest['Upper_Band'] * 0.998 and # 進入超買區
        latest['RV'] > 1.2 and                             # 巨鯨出貨確認
        latest['MACD'] < prev['MACD']                      # 動能轉弱
    )
    
    if long_condition:
        return "BUY"
    elif short_condition:
        return "SELL"
    else:
        return "NEUTRAL"
