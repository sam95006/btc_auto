import time
import threading
import os
import sys
from datetime import datetime
from core.datafeed import DataFeed
from strategy.indicators import calculate_all
from strategy.strategy import check_signal_scalper, check_signal_sniper, get_support_resistance_levels
from core.execution import PaperTrader
from core.storage import Storage
from core.notifier import send_line
from webhook import app as webhook_app
from strategy.learning import AdaptiveMLPredictor, ReflectionEngine
from sensors.sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner, TradingViewScanner
from strategy.performance_optimizer import PerformanceOptimizer
from strategy.market_regime_detector import MarketRegimeDetector
from agents.market_scanner import DynamicMarketScanner
from core.intelligence_center import IntelligenceCenter, AIRoundTable

# 1. 配置多幣種監控名單
MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
PEPE_SYMBOL = 'PEPE/USDT'  # PEPE 無限交易額度
DYNAMIC_SCAN_ENABLED = True  # 啟用動態市場掃描
TOP_SYMBOLS_SCAN = 20  # 動態掃描前20大幣種

def trading_loop(traders, predictor, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners, pepe_symbol, dynamic_scan_cash):
    print(f"🚀 【後台數據大腦】 啟動中 ...")
    
    # 初始化核心系統
    optimizer = PerformanceOptimizer(storage)
    regime_detector = MarketRegimeDetector(storage)
    intel_center = IntelligenceCenter(storage)
    # 此時 predictors 尚未在 trading_loop 範圍內定義，我們改用傳入的 active_predictors
    roundtable = AIRoundTable(traders, active_predictors, storage) 
    
    optimization_counter = 0 
    
    # 延遲初始化：讓 Webhook 先對外連線
    time.sleep(5) 
    
    # 初始化預設預測器 (避免在循環中引用未定義變量)
    active_predictors = {sym: AdaptiveMLPredictor(symbol=sym, storage=storage) for sym in MONITOR_SYMBOLS}
    active_predictors[pepe_symbol] = AdaptiveMLPredictor(symbol=pepe_symbol, storage=storage)

    for sym in MONITOR_SYMBOLS:
        try:
            print(f"⌛ 正在初始化 {sym} 情報...")
            df = calculate_all(feed_manager[sym].fetch_ohlcv(timeframe='1m', limit=500))
            active_predictors[sym].train(df)
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
                symbol_predictor = active_predictors.get(sym)
                
                # 抓取技術面數據
                df_1m = calculate_all(feed.fetch_ohlcv(timeframe='1m', limit=100))
                df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
                df_1h = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=50))
                
                # 🧠 全球機制 1: BTC 大盤崩盤保險
                btc_feed = feed_manager.get('BTC/USDT')
                btc_crash = False
                if btc_feed and sym != 'BTC/USDT':
                    btc_1m = btc_feed.fetch_ohlcv(timeframe='1m', limit=5)
                    if not btc_1m.empty and len(btc_1m) >= 2:
                        btc_change = (btc_1m.iloc[-1]['close'] - btc_1m.iloc[0]['close']) / btc_1m.iloc[0]['close']
                        if btc_change < -0.005: 
                            btc_crash = True

                # 🧠 全球機制 2: 15m 趨勢過濾 (EMA共振)
                m15_ema200 = df_15m.iloc[-1].get('EMA200', df_1m.iloc[-1]['close'])
                m15_trend_up = df_1m.iloc[-1]['close'] > m15_ema200

                # 🧠 全球機制 3: 資金費率陷阱逃頂
                fr = feed.get_funding_rate()
                extreme_funding = fr > 0.0004 # 資金費率過高，多頭危險
                
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
                
                # 🤖 幣種專屬 ML 預測
                ml_prob = symbol_predictor.predict_prob(df_1m.iloc[-1], funding_rate=fr, market_context={
                    'rsi': df_1m.iloc[-1].get('RSI', 50),
                    'volatility': df_1m['close'].pct_change().std(),
                    'ema200': m15_ema200
                })
                
                # 策略決策
                scalper_signal = check_signal_scalper(
                    df_1m, df_15m, df_1h, 
                    ml_prob, whale.get_whale_move(feed.exchange), news.fetch_latest_sentiment(), 0, 
                    funding_rate=fr, btc_change=0, sym_change=0,
                    market_regime={'regime': regime_name, 'volatility': df_1m['close'].pct_change().std()},
                    optimized_params=adjusted_params
                )
                
                # 【防禦邏輯介入】
                if btc_crash and scalper_signal == "BUY_SCALP":
                    scalper_signal = "HOLD" # 大盤跳水，暫停做多
                if extreme_funding and scalper_signal == "BUY_SCALP":
                    pass
                
                # 執行引擎
                context = {
                    'rsi': df_1m.iloc[-1].get('RSI', 50),
                    'ema200': m15_ema200,
                    'trend_15m': "UP" if m15_trend_up else "DOWN",
                    'ml_prob': ml_prob,
                    'rv': df_1m.iloc[-1].get('RV', 1.0),
                    'btc_crash': btc_crash,
                    'is_extreme_funding': extreme_funding,
                    'regime': regime_name
                }
                
                report = trader.execute(scalper_signal, "HOLD", df_1m.iloc[-1]['close'], storage, atr=df_1m.iloc[-1]['ATR'], context=context)
                
                if report:
                    tag = f"【{sym.replace('/USDT','')}】"
                    send_line(tag + "\n" + report)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} {report}")
            
            # 🧠 靈魂更新：全域情報數據更新 (每 5 分鐘一次)
            if optimization_counter % 10 == 0:
                intel_center.update_global_intelligence(
                    news_data={'sentiment': news.fetch_latest_sentiment()},
                    stock_data={'change_pct': macro.get_tech_stock_pulse() - 1.0}, # 轉化為百分比變化
                    fed_data={'sentiment': fed.get_sentiment()}
                )

            # 🤝 圓桌會議：AI 群體互學 (每 6 小時一次 = 720 個週期)
            if optimization_counter % 720 == 0:
                roundtable_report = roundtable.conduct_meeting()
                send_line("🤝 【AI 戰略互學圓桌會議】\n" + roundtable_report)
                
            time.sleep(30)
        except Exception as e:
            print(f"運行異常: {e}")
            time.sleep(10)

def market_scanning_loop(scanner, traders, feed_manager, storage, predictors, dynamic_scan_cash):
    """
    【動態監控大腦】: 隨時掃描市場符合條件的幣種並執行試探性下單
    """
    print("🔎 動態市場監控系統啟動...")
    while True:
        try:
            # 1. 執行市場掃描 (排除已有核心幣種)
            qualified = scanner.scan_market(limit=TOP_SYMBOLS_SCAN)
            
            # 2. 獲取評分最高的機會進行試探
            opportunities = scanner.get_top_opportunities(limit=2)
            
            for opp in opportunities:
                symbol = opp['symbol']
                
                # 如果還沒有這個幣種的交易員，且掃描幣種數量尚未超過限制
                if symbol not in traders and len(traders) < 10:
                    print(f"🎯 發現潛在標的 {symbol}，準備進行彈性下單測試...")
                    
                    # 初始化該幣種的 DataFeed
                    feed_manager[symbol] = DataFeed(symbol=symbol)
                    
                    # 使用彈性資金分配的小部分進行測試 (分配約 1/3 的動態資金)
                    test_cash = dynamic_scan_cash / 3
                    
                    # 建立試探性交易員
                    traders[symbol] = PaperTrader(
                        symbol=symbol, 
                        initial_cash=test_cash, 
                        max_daily_trades=5, 
                        is_pepe=False
                    )
                    
                    # 發送通知
                    send_line(f"🚀 【動態發現】\n掃描器發現符合條件幣種: {symbol}\n評分: {opp['scores']}\n已撥入試探資金: ${test_cash:.2f}")

            # 每 5 分鐘掃描一次，避免過於頻繁
            time.sleep(300) 
        except Exception as e:
            print(f"❌ 掃描循環異常: {e}")
            time.sleep(60)

def main():
    # 🚨 延後初始化: 將所有連線 API 的動作移到背景執行緒
    def async_init():
        try:
            print("⏳ 正在背景初始化交易核心與感測器...")
            
            # 🔧 數據庫初始化與安全檢查
            print("\n【📊 數據庫初始化】")
            storage = Storage()
            
            # 驗證數據庫完整性
            if not storage.verify_database_integrity():
                print("⚠️ 警告: 數據庫完整性檢查失敗，將基於現有數據繼續運行")
            
            # 自動備份
            backup_path = storage.backup_database()
            if backup_path:
                print(f"✅ 歷史成交記錄已備份，可恢復")
            
            # 查詢並顯示歷史統計
            lifetime_pnl, lifetime_trades = storage.get_lifetime_summary()
            print(f"\n【📈 歷史累計統計】")
            print(f"✅ 生涯交易總筆數: {lifetime_trades if lifetime_trades else 0}")
            print(f"✅ 生涯累計盈虧: ${lifetime_pnl if lifetime_pnl else 0:+.2f}")
            print(f"✅ 歷史學習資料: 已保留")
            print()
            
            # 所有幣種共用同一個大腦數據庫，但擁有獨立的預測器
            predictors = {sym: AdaptiveMLPredictor(symbol=sym, storage=storage) for sym in MONITOR_SYMBOLS}
            predictors[PEPE_SYMBOL] = AdaptiveMLPredictor(symbol=PEPE_SYMBOL, storage=storage)

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
            
            # 資金分配
            per_symbol_cash = total_initial_cash * 0.2
            pepe_cash = total_initial_cash * 0.15
            dynamic_scan_cash = total_initial_cash * 0.15
            
            # 初始化核心幣種
            for sym in MONITOR_SYMBOLS:
                try:
                    feed_manager[sym] = DataFeed(symbol=sym)
                    traders[sym] = PaperTrader(symbol=sym, initial_cash=per_symbol_cash, is_pepe=False)
                    whales[sym] = WhaleWatcher(symbol=sym.replace('/',''))
                    tv_scanners[sym] = TradingViewScanner(symbol=sym)
                    predictors[sym] = AdaptiveMLPredictor(symbol=sym, storage=storage) # 專屬學習器
                except Exception as sym_err:
                    print(f"⚠️ {sym} 初始化部分失敗: {sym_err}")
            
            # 初始化 PEPE 交易者 (無限交易額度)
            try:
                feed_manager[PEPE_SYMBOL] = DataFeed(symbol=PEPE_SYMBOL)
                traders[PEPE_SYMBOL] = PaperTrader(symbol=PEPE_SYMBOL, initial_cash=pepe_cash, max_daily_trades=999, is_pepe=True)
                whales[PEPE_SYMBOL] = WhaleWatcher(symbol=PEPE_SYMBOL.replace('/',''))
                tv_scanners[PEPE_SYMBOL] = TradingViewScanner(symbol=PEPE_SYMBOL)
            except Exception as pepe_err:
                print(f"⚠️ PEPE 初始化失敗: {pepe_err}")

            # 2. 啟動背景交易循環
            trading_thread = threading.Thread(target=trading_loop, args=(traders, predictors, feed_manager, storage, macro, whales, news, fed, pol, tv_scanners, PEPE_SYMBOL, dynamic_scan_cash))
            trading_thread.daemon = True
            trading_thread.start()

            # 3. 啟動市場掃描循環
            scanner = DynamicMarketScanner(storage=storage)
            scanning_thread = threading.Thread(target=market_scanning_loop, args=(scanner, traders, feed_manager, storage, predictors, dynamic_scan_cash))
            scanning_thread.daemon = True
            scanning_thread.start()

            print("✅ 背景交易與掃描系統已全數上線！")
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
