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
from sensors import MacroScanner, WhaleWatcher, NewsAI
from datetime import datetime
import os

def run_webhook():
    try:
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Webhook 啟動失敗: {e}")

def trading_loop(trader, predictor, feed, storage, macro, whale, news):
    print("🚀 【BTC 終極獵手：全知全能版】 啟動監控中 (News/Macro/Whale)...")
    init_data = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=500))
    predictor.train(init_data)

    while True:
        try:
            # 1. MTF 技術盤位
            df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
            
            # 2. 資金費率 (心理)
            fr = feed.get_funding_rate()
            
            # 3. 巨鯨力場 (Whale Orders)
            whale_ratio = whale.get_whale_move(feed.exchange)
            
            # 4. 宏觀趨勢 (SPX/DXY)
            macro_sig = macro.get_macro_signal()
            
            # 5. AI 合成信心 (包含情緒初步修正)
            latest_bar = df_1m.iloc[-1]
            ml_prob = predictor.predict_prob(latest_bar, funding_rate=fr)
            
            # 6. 全維度 Fusion 策略判定
            signal = check_signal(df_1m, df_15m, df_1h, ml_prob=ml_prob, whale_ratio=whale_ratio, macro_signal=macro_sig)
            
            price = latest_bar['close']
            atr = latest_bar['ATR']
            
            # 7. 進場執行 (與 ATR 動止損)
            trade_report = trader.execute(signal, price, storage, ml_prob=ml_prob, atr=atr)
            
            if trade_report:
                send_line(trade_report)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {trade_report}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] P:${price:,.2f} | AI:{ml_prob:.1%} | Whale:{whale_ratio:.2f} | FR:{fr:.4%}")

            time.sleep(60)
        except Exception as e:
            print(f"背景循環異常: {e}")
            time.sleep(10)

def main():
    feed = DataFeed(symbol='BTC/USDT')
    try: storage = Storage()
    except: storage = None
    
    predictor = MLPredictor()
    macro = MacroScanner()
    whale = WhaleWatcher()
    news = NewsAI()
    
    trader = PaperTrader(initial_cumulative_pnl=-43.87)
    
    trading_thread = threading.Thread(target=trading_loop, args=(trader, predictor, feed, storage, macro, whale, news))
    trading_thread.daemon = True
    trading_thread.start()

    run_webhook()

if __name__ == "__main__":
    main()
