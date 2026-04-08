import time
import threading
import os
from datetime import datetime
from datafeed import DataFeed
from indicators import calculate_all
from strategy import check_signal_scalper, check_signal_sniper
from execution import PaperTrader
from storage import Storage
from notifier import send_line
from webhook import app as webhook_app
from learning import MLPredictor
from sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner, TradingViewScanner

# 1. 配置多幣種監控名單
MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PEPE/USDT']

def trading_loop(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners):
    print(f"🚀 【後台數據大腦】 啟動中 ...")
    
    # 延遲初始化：讓 Webhook 先對外連線
    time.sleep(5) 
    
    for sym in MONITOR_SYMBOLS:
        try:
            print(f"⌛ 正在初始化 {sym} 情報...")
            df = calculate_all(feed_manager[sym].fetch_ohlcv(timeframe='1m', limit=500))
            predictor.train(df)
        except Exception as e:
            print(f"⚠️ {sym} 初始化失敗: {e}")

    prev_oi = {sym: 0 for sym in MONITOR_SYMBOLS}

    while True:
        try:
            for sym in MONITOR_SYMBOLS:
                feed = feed_manager[sym]
                trader = traders[sym]
                whale = whales[sym]
                tv = tv_scanners[sym]
                
                # 抓取技術面數據
                df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
                df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
                df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
                
                # 綜合感測器調研
                tv_score = tv.get_sentiment()
                whale_ratio = whale.get_whale_move(feed.exchange)
                news_score = news.fetch_latest_sentiment()
                
                # 流動性與 ML 信心
                current_oi = feed.get_open_interest()
                oi_delta = (current_oi - prev_oi[sym]) / prev_oi[sym] if prev_oi.get(sym, 0) > 0 else 0
                prev_oi[sym] = current_oi
                fr = feed.get_funding_rate()
                
                # 計算相對強度與波動率所需的數據
                btc_df = feed_manager['BTC/USDT'].fetch_ohlcv(timeframe='1h', limit=24)
                btc_change = (btc_df.iloc[-1]['close'] - btc_df.iloc[0]['close']) / btc_df.iloc[0]['close'] if not btc_df.empty else 0
                
                sym_24h_df = feed.fetch_ohlcv(timeframe='1h', limit=24)
                sym_change = (sym_24h_df.iloc[-1]['close'] - sym_24h_df.iloc[0]['close']) / sym_24h_df.iloc[0]['close'] if not sym_24h_df.empty else 0

                latest_bar = df_1m.iloc[-1]
                ml_prob = predictor.predict_prob(latest_bar, funding_rate=fr)
                price = latest_bar['close']
                atr = latest_bar['ATR']
                
                # 策略決策 (傳入相對強度數據)
                scalper_signal = check_signal_scalper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, funding_rate=fr, btc_change=btc_change, sym_change=sym_change)
                sniper_signal = check_signal_sniper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, 1.1, 0.6, 0.6, funding_rate=fr, tv_score=tv_score)
                
                # 封裝環境變數供反思使用
                context = {
                    'rsi': latest_bar.get('RSI', 50),
                    'ema200': latest_bar.get('EMA_200', price),
                    'atr': atr,
                    'ml_prob': ml_prob,
                    'volatility': df_1m['close'].std()
                }
                
                # 執行引擎扣板機
                report = trader.execute(scalper_signal, sniper_signal, price, storage, atr=atr, context=context)
                
                if report:
                    tag = f"【{sym.replace('/USDT','')}】"
                    send_line(tag + "\n" + report)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} {report}")

            time.sleep(30)
        except Exception as e:
            print(f"運行異常: {e}")
            time.sleep(10)

def main():
    # 🚨 延後初始化: 將所有連線 API 的動作移到背景執行緒
    def async_init():
        try:
            print("⏳ 正在背景初始化交易核心與感測器...")
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
                try:
                    feed_manager[sym] = DataFeed(symbol=sym)
                    limit = 10 if "BTC" in sym else 999
                    traders[sym] = PaperTrader(symbol=sym, initial_cash=2500, max_daily_trades=limit)
                    whales[sym] = WhaleWatcher(symbol=sym.replace('/',''))
                    tv_scanners[sym] = TradingViewScanner(symbol=sym)
                except Exception as sym_err:
                    print(f"⚠️ {sym} 初始化部分失敗 (跳過繼續): {sym_err}")

            # 2. 啟動背景交易循環
            trading_thread = threading.Thread(target=trading_loop, args=(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners))
            trading_thread.daemon = True
            trading_thread.start()
            print("✅ 背景交易系統已全數上線！")
        except Exception as init_err:
            print(f"❌ 背景初始化失敗: {init_err}")

    # 立即觸發異步初始化，主線程不再等待
    init_thread = threading.Thread(target=async_init)
    init_thread.daemon = True
    init_thread.start()

    # 讓主線程運行 Flask 應用
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 啟動 Flask 應用於 Port {port} ...")
    webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
