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
from sensors import MacroScanner, WhaleWatcher
from datetime import datetime
import os

def run_webhook():
    try:
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Webhook 啟動失敗: {e}")

def trading_loop(trader, predictor, feed, storage, macro, whale):
    print("🚀 【BTC 終極獵手：精英情緒版】 啟動中 (F&G Index + Whale Watcher)...")
    init_data = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=500))
    predictor.train(init_data)

    while True:
        try:
            # 1. 抓取多維度時間框架 (MTF)
            df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
            
            # 2. 抓取全網心理情緒 (Fear & Greed Index)
            fng_score = macro.get_sentiment_score()
            
            # 3. 巨鯨力場偵測 (Whale Orders)
            whale_ratio = whale.get_whale_move(feed.exchange)
            
            # 4. 資金費率 (Leverage Sentiment)
            fr = feed.get_funding_rate()
            
            # 5. 合成 AI 決策信心 (F&G 修正)
            latest_bar = df_1m.iloc[-1]
            ml_prob = predictor.predict_prob(latest_bar, funding_rate=fr)
            
            # 6. 進場判定
            signal = check_signal(df_1m, df_15m, df_1h, ml_prob=ml_prob, whale_ratio=whale_ratio)
            
            price = latest_bar['close']
            atr = latest_bar['ATR']
            
            # 7. 執行引擎 (ATR 波動止損)
            trade_report = trader.execute(signal, price, storage, ml_prob=ml_prob, atr=atr)
            
            if trade_report:
                send_line(trade_report)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {trade_report}")
            else:
                # 定時印出一條狀態日誌至伺服器
                print(f"[{datetime.now().strftime('%H:%M:%S')}] P:${price:,.2f} | AI:{ml_prob:.1%} | F&G:{fng_score:.2f} | Whale:{whale_ratio:.2f}")

            time.sleep(60)
        except Exception as e:
            print(f"背景巡邏異常: {e}")
            time.sleep(10)

def main():
    feed = DataFeed(symbol='BTC/USDT')
    try: storage = Storage()
    except: storage = None
    
    predictor = MLPredictor()
    macro = MacroScanner()
    whale = WhaleWatcher()
    
    # 基線帳戶平衡
    trader = PaperTrader(initial_cumulative_pnl=-43.87)
    
    # 啟動背景線程
    trading_thread = threading.Thread(target=trading_loop, args=(trader, predictor, feed, storage, macro, whale))
    trading_thread.daemon = True
    trading_thread.start()

    run_webhook()

if __name__ == "__main__":
    main()
