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
from sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner, TradingViewScanner
from datetime import datetime
import os

# 1. 配置多幣種監控名單
MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PEPE/USDT']

def run_webhook():
    try:
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Webhook 啟動失敗: {e}")

def trading_loop(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners):
    print(f"🚀 【全方位全知系統】 啟動中 ...")
    
    # 初始化數據
    for sym in MONITOR_SYMBOLS:
        print(f"⌛ 正在初始化 {sym} 數據...")
        df = calculate_all(feed_manager[sym].fetch_ohlcv(timeframe='1m', limit=500))
        predictor.train(df)

    prev_oi = {sym: feed_manager[sym].get_open_interest() for sym in MONITOR_SYMBOLS}

    while True:
        try:
            for sym in MONITOR_SYMBOLS:
                feed = feed_manager[sym]
                trader = traders[sym]
                whale = whales[sym]
                tv = tv_scanners[sym]
                
                # 抓取多維數據
                df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
                df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
                df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
                
                # 獲取 TradingView 的綜合看漲/看跌分數
                tv_score = tv.get_sentiment()
                
                # 巨鯨動態 (Orderbook Imbalance)
                whale_ratio = whale.get_whale_move(feed.exchange)
                
                # 宏觀與新聞
                news_score = news.fetch_latest_sentiment()
                # 資金流動性
                current_oi = feed.get_open_interest()
                oi_delta = (current_oi - prev_oi[sym]) / prev_oi[sym] if prev_oi[sym] > 0 else 0
                prev_oi[sym] = current_oi
                fr = feed.get_funding_rate()
                
                latest_bar = df_1m.iloc[-1]
                ml_prob = predictor.predict_prob(latest_bar, funding_rate=fr)
                price = latest_bar['close']
                atr = latest_bar['ATR']
                
                # 策略評估 (整合 TV 分數)
                scalper_signal = check_signal_scalper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, funding_rate=fr, tv_score=tv_score)
                sniper_signal = check_signal_sniper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, 1.1, 0.6, 0.6, funding_rate=fr, tv_score=tv_score)
                
                # [反思數據收集]: 收集目前的市場環境，供複盤使用
                context = {
                    'rsi': latest_bar.get('RSI', 50),
                    'ema200': latest_bar.get('EMA_200', price),
                    'atr': atr,
                    'ml_prob': ml_prob,
                    'volatility': df_1m['close'].std()
                }
                
                # 執行
                report = trader.execute(scalper_signal, sniper_signal, price, storage, atr=atr, context=context)
                
                if report:
                    tag = f"【{sym.replace('/USDT','')}】"
                    send_line(tag + "\n" + report)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} {report}")

            time.sleep(30) # 為了 PEPE 與極短線，再次縮短輪詢間隔
        except Exception as e:
            print(f"監控異常: {e}")
            time.sleep(10)

def main():
    storage = Storage()
    predictor = MLPredictor()
    macro = MacroScanner()
    news = NewsScanner()
    fed = FedScanner()
    pol = PoliticalScanner()

    feed_manager = {}
    traders = {}
    whales = {}
    tv_scanners = {}
    
    for sym in MONITOR_SYMBOLS:
        feed_manager[sym] = DataFeed(symbol=sym)
        limit = 10 if "BTC" in sym else 999
        traders[sym] = PaperTrader(symbol=sym, initial_cash=2500, max_daily_trades=limit)
        whales[sym] = WhaleWatcher(symbol=sym.replace('/',''))
        tv_scanners[sym] = TradingViewScanner(symbol=sym)

    trading_thread = threading.Thread(target=trading_loop, args=(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners))
    trading_thread.daemon = True
    trading_thread.start()

    run_webhook()

if __name__ == "__main__":
    main()
