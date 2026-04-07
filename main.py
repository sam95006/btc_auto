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
    print("📈 背景交易監控執行緒已啟動...")
    # 首次開機進行訓練 (輕量化 500 根)
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
            
            # 2. AI 信心評估
            ml_prob = predictor.predict_prob(df_1m.iloc[-1])
            
            # 3. 三維時空共振策略判定 (+AI 過濾)
            signal = check_signal(df_1m, df_15m, df_1h, ml_prob=ml_prob)
            
            latest_1m = df_1m.iloc[-1]
            price = latest_1m['close']
            
            # --- 安全存儲記錄 ---
            if storage:
                try:
                    storage.log_signal(signal, price, latest_1m['RSI'], latest_1m['MACD'])
                except:
                    pass
                    
            trade_report = trader.execute(signal, price, storage)
            
            if trade_report:
                msg = f"{trade_report} (AI信心: {ml_prob:.1%})"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
                send_line(msg)
            else:
                # 靜默執行，每分鐘印一條行情日誌
                rpt_line = (f"[{datetime.now().strftime('%H:%M:%S')}] "
                            f"Price: ${price:,.2f} | AI機率: {ml_prob:.1%} | 趨勢: {signal}")
                print(rpt_line)
            
            # 4. 每 60 分鐘重新進行一次自適應學習
            loop_count += 1
            if loop_count >= 60:
                print("--- 🧠 啟動每小時自適應學習週期 ---")
                train_data = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=1000))
                predictor.train(train_data)
                loop_count = 0
                
            time.sleep(60)
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 出錯: {e}")
            time.sleep(10)

def main():
    feed = DataFeed(symbol='BTC/USDT')
    
    # 資料庫初始化容逃保護
    try:
        storage = Storage()
    except Exception as e:
        print(f"資料庫連結警告: {e}")
        storage = None
    
    # 建立自適應預測大腦
    predictor = MLPredictor()
    
    # 強制對齊虧損基線 (-43.87)
    last_pnl = -43.87
    trader = PaperTrader(initial_cumulative_pnl=last_pnl)
    
    print("-" * 40)
    print("🚀 BTCUSDT AI 自適應系統 (穩定版) 啟動中...")
    print("-" * 40)

    # 🚀 啟動背景交易監控執行緒
    trading_thread = threading.Thread(target=trading_loop, args=(trader, predictor, feed, storage))
    trading_thread.daemon = True
    trading_thread.start()

    # 🚀 主執行緒：執行 Webhook (讓 Render 秒速抓到埠位)
    run_webhook()

if __name__ == "__main__":
    main()
