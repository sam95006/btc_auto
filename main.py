import time
import threading
import os
import sys
from datetime import datetime
from datafeed import DataFeed
from indicators import calculate_all
from strategy import check_signal_scalper, check_signal_sniper, get_support_resistance_levels
from execution import PaperTrader
from storage import Storage
from notifier import send_line
from webhook import app as webhook_app
from learning import AdaptiveMLPredictor
from sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner, TradingViewScanner
from performance_optimizer import PerformanceOptimizer
from market_regime_detector import MarketRegimeDetector

# 1. 配置多幣種監控名單
MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
PEPE_SYMBOL = 'PEPE/USDT'  # PEPE 無限交易額度
DYNAMIC_SCAN_ENABLED = True  # 啟用動態市場掃描
TOP_SYMBOLS_SCAN = 20  # 動態掃描前20大幣種

def trading_loop(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners, pepe_symbol, dynamic_scan_cash):
    print(f"🚀 【後台數據大腦】 啟動中 ...")
    
    # 初始化優化系統
    optimizer = PerformanceOptimizer(storage)
    regime_detector = MarketRegimeDetector(storage)
    optimization_counter = 0  # 每 7 分鐘優化一次 (14 個 30 秒週期)
    
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
            optimization_counter += 1
            
            for sym in MONITOR_SYMBOLS:
                feed = feed_manager[sym]
                trader = traders[sym]
                whale = whales[sym]
                tv = tv_scanners[sym]
                
                # 抓取技術面數據
                df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
                df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
                df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
                
                # 🧠 定期優化參數 (每 7 分鐘一次)
                if optimization_counter % 14 == 0:
                    optimized_params = optimizer.optimize_parameters(sym, lookback_days=7)
                else:
                    optimized_params = optimizer.get_optimal_params(sym, use_cache=True)
                
                # 🌍 市場制度檢測
                regime_info = regime_detector.detect_regime(df_1h, sym)
                regime_name, regime_score, regime_desc = regime_info
                
                # 根據市場制度調整參數
                adjusted_params = optimizer.adjust_for_market_regime(optimized_params, {
                    'regime': regime_name,
                    'volatility': df_1m['close'].pct_change().std()
                })
                
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
                
                # 🤖 自適應 ML 預測 (使用自學習的參數)
                ml_predictor = AdaptiveMLPredictor(storage)
                ml_prob = ml_predictor.predict_prob(latest_bar, funding_rate=fr, market_context={
                    'rsi': latest_bar.get('RSI', 50),
                    'volatility': df_1m['close'].pct_change().std(),
                    'ema200': df_1h.iloc[-1].get('EMA200', latest_bar['close'])
                })
                
                price = latest_bar['close']
                atr = latest_bar['ATR']
                
                # 支撐/阻力識別
                support_zone, resistance_zone = get_support_resistance_levels(df_1h, period=20)
                
                # 📊 多時間框架確認機制
                m1_rsi = latest_bar.get('RSI', 50)
                m15_rsi = df_15m.iloc[-1].get('RSI', 50)
                h1_ema = df_1h.iloc[-1].get('EMA200', price)
                
                # 策略決策 (傳入市場制度、優化參數、多時間框架信息)
                scalper_signal = check_signal_scalper(
                    df_1m, df_15m, df_1h, 
                    ml_prob, whale_ratio, news_score, oi_delta, 
                    funding_rate=fr, btc_change=btc_change, sym_change=sym_change,
                    market_regime={'regime': regime_name, 'volatility': df_1m['close'].pct_change().std()},
                    optimized_params=adjusted_params
                )
                
                sniper_signal = check_signal_sniper(
                    df_1m, df_15m, df_1h, 
                    ml_prob, whale_ratio, news_score, oi_delta, 
                    tv_score, fed.get_sentiment(), pol.get_sentiment(),
                    funding_rate=fr,
                    market_regime={'regime': regime_name},
                    optimized_params=adjusted_params
                )
                
                # 📈 動態頭寸調整
                base_signal_confidence = 0.75 if scalper_signal in ["BUY_SCALP", "SELL_SCALP"] else 0.5
                signal_confidence = trader.multi_timeframe_confirmation(m1_rsi, m15_rsi, h1_ema, price, 
                                                                        direction="LONG" if scalper_signal == "BUY_SCALP" else "SHORT")
                
                position_size = trader.dynamic_position_sizing(signal_confidence, base_size=0.4)
                
                # 封裝環境變數供反思使用
                context = {
                    'rsi': m1_rsi,
                    'ema200': h1_ema,
                    'atr': atr,
                    'ml_prob': ml_prob,
                    'volatility': df_1m['close'].pct_change().std(),
                    'regime': regime_name,
                    'signal_confidence': signal_confidence,
                    'support': support_zone.get('primary', 0),
                    'resistance': resistance_zone.get('primary', 0)
                }
                
                # 執行引擎扣板機
                report = trader.execute(scalper_signal, sniper_signal, price, storage, atr=atr, context=context)
                
                if report:
                    tag = f"【{sym.replace('/USDT','')}】"
                    send_line(tag + "\n" + report)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} {report}")
                    
                    # 📊 市場制度信息 (定期報告)
                    if optimization_counter % 14 == 0:
                        regime_report = f"📡 市場制度: {regime_name} ({regime_score:.1%}) | {regime_desc}"
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {regime_report}")

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
            predictor = AdaptiveMLPredictor(storage)  # 使用自適應 ML 預測器
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
