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
from sensors import MacroScanner, WhaleWatcher, NewsScanner
from datetime import datetime
import os

def run_webhook():
    try:
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Webhook 啟動失敗: {e}")

def trading_loop(trader, predictor, feed, storage, macro, whale, news):
    print("🚀 【BTC 終極獵手：全知新聞版】 啟動中 (F&G + Whale + RSS News)...")
    init_data = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=500))
    predictor.train(init_data)

    while True:
        try:
            # 1. 抓取技術面
            df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
            
            # 2. 抓取外部感測面 (情緒 + 巨鯨 + 新聞)
            fng_score = macro.get_sentiment_score()
            whale_ratio = whale.get_whale_move(feed.exchange)
            news_score = news.fetch_latest_sentiment()
            
            # 3. 資金費率
            fr = feed.get_funding_rate()
            
            # 4. AI 信心評分
            latest_bar = df_1m.iloc[-1]
            ml_prob = predictor.predict_prob(latest_bar, funding_rate=fr)
            
            # 5. 【終極融合信號】 (加入新聞分數)
            signal = check_signal(df_1m, df_15m, df_1h, ml_prob=ml_prob, whale_ratio=whale_ratio, news_score=news_score)
            
            price = latest_bar['close']
            atr = latest_bar['ATR']
            
            # 6. 執行決策 (自適應斷路器 + 狀態持久化)
            trade_report = trader.execute(signal, price, storage, ml_prob=ml_prob, atr=atr)
            
            if trade_report:
                send_line(trade_report)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {trade_report}")
            else:
                # 定時日誌輸出
                status = (f"[{datetime.now().strftime('%H:%M:%S')}] P:${price:,.2f} | "
                          f"AI:{ml_prob:.1%} | News:{news_score:.2f} | Whale:{whale_ratio:.2f}")
                print(status)

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
    news = NewsScanner()
    
    # 以前的累積損益 (繼承狀態)
    trader = PaperTrader(initial_cumulative_pnl=-43.87)
    
    # 啟動背景監控執行緒
    trading_thread = threading.Thread(target=trading_loop, args=(trader, predictor, feed, storage, macro, whale, news))
    trading_thread.daemon = True
    trading_thread.start()

    run_webhook() # 主執行緒運行 Webhook

if __name__ == "__main__":
    main()
