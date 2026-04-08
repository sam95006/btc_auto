import time
import threading
from datafeed import DataFeed
from indicators import calculate_all
from strategy import check_signal_scalper, check_signal_sniper
from execution import PaperTrader
from storage import Storage
from notifier import send_line
from webhook import app as webhook_app
from learning import MLPredictor
from sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner
from datetime import datetime
import os

# 1. 配置多幣種監控名單
MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

def run_webhook():
    try:
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Webhook 啟動失敗: {e}")

def trading_loop(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol):
    print(f"🚀 【BTC+ETH+SOL 聯合獵手行動】 啟動中 ...")
    
    # 初始化數據
    for sym in MONITOR_SYMBOLS:
        print(f"⌛ 正在初始化 {sym} 數據與 AI 訓練...")
        df = calculate_all(feed_manager[sym].fetch_ohlcv(timeframe='1m', limit=500))
        predictor.train(df)

    prev_oi = {sym: feed_manager[sym].get_open_interest() for sym in MONITOR_SYMBOLS}

    while True:
        try:
            # 輪詢監控的幣種
            for sym in MONITOR_SYMBOLS:
                feed = feed_manager[sym]
                trader = traders[sym]
                whale = whales[sym]
                
                # 獲取多維數據 (1m, 15m)
                df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
                df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
                df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
                
                # 宏觀與籌碼
                fng_score = macro.get_sentiment_score()
                whale_ratio = whale.get_whale_move(feed.exchange)
                news_score = news.fetch_latest_sentiment()
                fed_score = fed.get_sentiment()
                pol_score = pol.get_sentiment()
                
                current_oi = feed.get_open_interest()
                oi_delta = (current_oi - prev_oi[sym]) / prev_oi[sym] if prev_oi[sym] > 0 else 0
                prev_oi[sym] = current_oi
                fr = feed.get_funding_rate()
                
                latest_bar = df_1m.iloc[-1]
                ml_prob = predictor.predict_prob(latest_bar, funding_rate=fr)
                price = latest_bar['close']
                atr = latest_bar['ATR']
                
                # 策略評估 (Scalper & Sniper)
                scalper_signal = check_signal_scalper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, funding_rate=fr)
                # sniper 暫時也餵進去
                sniper_signal = "HOLD" 
                
                # 執行下單
                report = trader.execute(scalper_signal, sniper_signal, price, storage, atr=atr)
                
                if report:
                    tag = f"【{sym.replace('/USDT','')}】"
                    send_line(tag + "\n" + report)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} {report}")

            time.sleep(40) # 縮短輪詢間隔，增加對 1m 線的捕捉速度
        except Exception as e:
            print(f"聯合監控異常: {e}")
            time.sleep(10)

def main():
    storage = Storage()
    predictor = MLPredictor()
    macro = MacroScanner()
    news = NewsScanner()
    fed = FedScanner()
    pol = PoliticalScanner()

    # 初始化各幣種的專屬物件
    feed_manager = {}
    traders = {}
    whales = {}
    
    initial_pnl, _ = storage.get_lifetime_summary()
    
    for sym in MONITOR_SYMBOLS:
        feed_manager[sym] = DataFeed(symbol=sym)
        # 資金分配：每個幣種共享模擬本金，但獨立管理倉位
        traders[sym] = PaperTrader(initial_cumulative_pnl=initial_pnl)
        whales[sym] = WhaleWatcher(symbol=sym.replace('/',''))

    trading_thread = threading.Thread(target=trading_loop, args=(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol))
    trading_thread.daemon = True
    trading_thread.start()

    run_webhook()

if __name__ == "__main__":
    main()
