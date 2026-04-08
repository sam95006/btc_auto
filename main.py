import time
import threading
import os
import sys
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
MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
PEPE_SYMBOL = 'PEPE/USDT'  # PEPE 無限交易額度
DYNAMIC_SCAN_ENABLED = True  # 啟用動態市場掃描
TOP_SYMBOLS_SCAN = 20  # 動態掃描前20大幣種

def trading_loop(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners, pepe_symbol, dynamic_scan_cash):
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
                sniper_signal = check_signal_sniper(df_1m, df_15m, df_1h, ml_prob, whale_ratio, news_score, oi_delta, tv_score, fed.get_sentiment(), pol.get_sentiment(), funding_rate=fr)
                
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
            
            # 總初始資金
            total_initial_cash = 10000
            
            # 資金分配：4個核心币種 + 1個PEPE + 1個動態掃描
            per_symbol_cash = total_initial_cash * 0.2  # 每個核心幣種 20%
            pepe_cash = total_initial_cash * 0.15  # PEPE 15%
            dynamic_scan_cash = total_initial_cash * 0.15  # 動態掃描 15%
            
            # 初始化核心4個幣種的交易者
            for sym in MONITOR_SYMBOLS:
                try:
                    feed_manager[sym] = DataFeed(symbol=sym)
                    limit = 10 if "BTC" in sym else 999
                    traders[sym] = PaperTrader(symbol=sym, initial_cash=per_symbol_cash, max_daily_trades=limit, is_pepe=False)
                    whales[sym] = WhaleWatcher(symbol=sym.replace('/',''))
                    tv_scanners[sym] = TradingViewScanner(symbol=sym)
                except Exception as sym_err:
                    print(f"⚠️ {sym} 初始化部分失敗 (跳過繼續): {sym_err}")
            
            # 初始化 PEPE 交易者 (無限交易額度)
            try:
                feed_manager[PEPE_SYMBOL] = DataFeed(symbol=PEPE_SYMBOL)
                traders[PEPE_SYMBOL] = PaperTrader(symbol=PEPE_SYMBOL, initial_cash=pepe_cash, max_daily_trades=999, is_pepe=True)
                whales[PEPE_SYMBOL] = WhaleWatcher(symbol=PEPE_SYMBOL.replace('/',''))
                tv_scanners[PEPE_SYMBOL] = TradingViewScanner(symbol=PEPE_SYMBOL)
            except Exception as pepe_err:
                print(f"⚠️ PEPE 初始化失敗: {pepe_err}")

            # 2. 啟動背景交易循環
            trading_thread = threading.Thread(target=trading_loop, args=(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners, PEPE_SYMBOL, dynamic_scan_cash))
            trading_thread.daemon = True
            trading_thread.start()
            print("✅ 背景交易系統已全數上線！")
        except Exception as init_err:
            print(f"❌ 背景初始化失敗: {init_err}")
            import traceback
            traceback.print_exc()

    # 立即觸發異步初始化，主線程不再等待
    init_thread = threading.Thread(target=async_init)
    init_thread.daemon = True
    init_thread.start()

    # 讓主線程運行 Flask 應用 - 這是 Zeabur 期望的主進程
    try:
        port = int(os.environ.get('PORT', 8080))
        print(f"🚀 啟動 Flask 應用於 Port {port} ...")
        sys.stdout.flush()  # 確保日誌立即輸出
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"❌ Flask 啟動失敗: {e}")
        import traceback
        traceback.print_exc()
        # 繼續運行以讓 Zeabur 能連接
        time.sleep(999999)

if __name__ == "__main__":
    main()
