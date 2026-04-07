import time
import threading
from datafeed import DataFeed
from indicators import calculate_all
from strategy import check_signal
from execution import PaperTrader
from storage import Storage
from notifier import send_line
from webhook import app as webhook_app
from learning import MLPredictor
from datetime import datetime
import os

def run_webhook():
    try:
        port = int(os.environ.get('PORT', 8080))
        print(f"啟動 Webhook 服務 (Port {port})...")
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Webhook 啟動失敗: {e}")

def trading_loop(trader, predictor, feed, storage):
    print("📈 背景交易監控執行緒已啟動 (終極 AI 版)...")
    try:
        init_data = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=500))
        predictor.train(init_data)
    except Exception as e:
        print(f"初期訓練失敗: {e}")

    loop_count = 0
    while True:
        try:
            # 1. 抓取多維度時間框架 (MTF)
            df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
            
            # 2. 抓取全網心理數據 (Funding Rate)
            fr = feed.get_funding_rate()
            
            # 3. 提取最新的波動率 (ATR)
            latest_bar = df_1m.iloc[-1]
            atr = latest_bar['ATR']
            
            # 4. 合成 AI 信心評估 (已內建情緒修正)
            ml_prob = predictor.predict_prob(latest_bar, funding_rate=fr)
            
            # 5. 三維時空共振策略判定
            signal = check_signal(df_1m, df_15m, df_1h, ml_prob=ml_prob)
            
            price = latest_bar['close']
            
            # --- 數據安全存儲 ---
            if storage:
                try: storage.log_signal(signal, price, latest_bar['RSI'], latest_bar['MACD'])
                except: pass
                    
            # 6. 核心執行決策 (內建 ATR 追蹤止損)
            trade_report = trader.execute(signal, price, storage, ml_prob=ml_prob, atr=atr)
            
            if trade_report:
                time_str = datetime.now().strftime('%H:%M:%S')
                msg = f"【🔥 頂級 AI 決策發布】\n{trade_report}\n------------------\nAI信心: {ml_prob:.1%} | 波動(ATR): {atr:.2f} | 費率: {fr:.4%}"
                print(f"[{time_str}] {msg}")
                send_line(msg)
            else:
                # 靜默行情巡邏日誌
                rpt_line = (f"[{datetime.now().strftime('%H:%M:%S')}] "
                            f"Price: ${price:,.2f} | AI機率: {ml_prob:.1%} | 趨勢: {signal} | 費率: {fr:.4%}")
                print(rpt_line)
            
            # 每 60 分鐘重新學習一次最近行情
            loop_count += 1
            if loop_count >= 60:
                print("--- 🧠 啟動每小時自適應學習周期 (增加大數據特徵) ---")
                train_data = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=1000))
                predictor.train(train_data)
                loop_count = 0
                
            time.sleep(60)
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 背景循環異常: {e}")
            time.sleep(10)

def main():
    feed = DataFeed(symbol='BTC/USDT')
    try:
        storage = Storage()
    except Exception as e:
        print(f"資料庫警告: {e}")
        storage = None
        
    predictor = MLPredictor()
    last_pnl = -43.87 # 前面累積的真金白銀損益
    trader = PaperTrader(initial_cumulative_pnl=last_pnl)
    
    print("-" * 40)
    print("🚀 BTC 終極獵手 (Enterprise Elite) 啟動...")
    print("-" * 40)

    trading_thread = threading.Thread(target=trading_loop, args=(trader, predictor, feed, storage))
    trading_thread.daemon = True
    trading_thread.start()

    run_webhook() # 主執行緒保持通暢

if __name__ == "__main__":
    main()
