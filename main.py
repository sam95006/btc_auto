import time
import threading
import os
import sys
import json
from datetime import datetime

# ==========================================
# 【核心修復：路徑抬升系統】
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT_DIR)
for folder in ['core', 'strategy', 'sensors', 'agents']:
    sys.path.append(os.path.join(ROOT_DIR, folder))

try:
    from core.datafeed import DataFeed
    from strategy.indicators import calculate_all
    from core.execution import PaperTrader
    from core.storage import Storage
    from core.notifier import send_line
    from webhook import app as webhook_app
    from strategy.learning import AdaptiveMLPredictor
    from sensors.sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner, TradingViewScanner
    from strategy.performance_optimizer import PerformanceOptimizer
    from strategy.market_regime_detector import MarketRegimeDetector
    from agents.market_scanner import DynamicMarketScanner
    from core.intelligence_center import IntelligenceCenter, AIRoundTable
    from strategy.consensus import ChiefAnalyst
except ImportError as e:
    print(f"❌ 導入失敗: {e}")

# --- [自癒監察官] 全局狀態監控 ---
AGENT_HEALTH = {} 

def update_heartbeat(symbol, status="OK", mode="BATTLE"):
    AGENT_HEALTH[symbol] = {
        'status': status,
        'mode': mode,
        'last_heartbeat': time.time(),
        'time_str': datetime.now().strftime("%H:%M:%S")
    }
    webhook_app.agent_status = AGENT_HEALTH

def agent_worker(symbol, trader, predictor, feed, storage, macro, whale, news, fed, pol, tv, chiefs):
    """
    【特工獨立作戰單元】: 每個師團獨立運作，具備強大自癒能力。
    當發現異常會自動休眠後重啟，並從資料庫恢復持倉繼續作戰。
    """
    print(f"🕵️ 【特工分隊啟動】: {symbol} 派遣完成。")
    
    while True:
        try:
            # --- [大都會自癒心跳] ---
            storage.save_global_config(f"HEALTH_{symbol}", "OK")
            storage.save_global_config(f"LAST_ACT_{symbol}", datetime.now().strftime("%H:%M:%S"))
            
            # --- [數據初始化] ---
            trader.load_active_position()
            
            # --- [數據獲取與智慧節能] ---
            df_1m = feed.fetch_ohlcv(timeframe='1m', limit=100)
            if df_1m.empty or len(df_1m) < 20:
                time.sleep(20)
                continue
            
            current_price = float(df_1m['close'].iloc[-1])
            storage.save_global_config(f"PRICE_{symbol}", str(current_price))
            
            # 效能智慧調節 (Eco-Tactical Balancing)
            recent_mv = (df_1m['high'].iloc[-5:].max() - df_1m['low'].iloc[-5:].min()) / current_price
            sleep_time, mode = (180, "ECO") if recent_mv < 0.001 else (45, "BATTLE")
            
            # --- [計算技術指標] ---
            df_1m = calculate_all(df_1m)
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            
            # --- [外部情緒感知與行情數據] ---
            funding_score = feed.get_funding_rate() if hasattr(feed, 'get_funding_rate') else 0.0001
            ls_score = 0.5 # 預設中立
            whale_score = 1.0
            if datetime.now().minute % 5 == 0:
                whale_score = whale.get_whale_move(feed.exchange) if whale else 1.0
                storage.save_global_config("WHALE_MVT", "Stable Accumulation" if whale_score < 2.5 else "Volatility Alert!")
            
            update_heartbeat(symbol, "OK", mode)
            
            # --- [C. AI 決策與執行] ---
            ml_prob = predictor.predict_prob(df_1m.iloc[-1]) if predictor else 0.5
            
            global_context = {
                'ml_prob': ml_prob,
                'whale_score': whale_score,
                'news_sentiment': news.fetch_latest_sentiment() if news else 0.5,
                'fng_score': macro.get_sentiment_score() if macro else 0.5,
                'funding_sentiment': funding_score,
                'ls_ratio': ls_score,
                'global_bias': 0.6
            }
            
            # 組長最後拍板
            team_signal, team_conf = chiefs[symbol].make_final_decision(df_1m, df_15m, global_context)
            
            scalper_signal = "HOLD"
            if team_signal == "BUY": scalper_signal = "BUY_SCALP"
            elif team_signal == "SELL": scalper_signal = "SELL_SCALP"

            report = trader.execute(scalper_signal, "HOLD", current_price, storage=storage, atr=df_1m.iloc[-1].get('ATR', 0), 
                                    context={'rsi': df_1m.iloc[-1].get('RSI', 50), 'ml_prob': ml_prob, 'whale_score': whale_score})
            
            if report:
                send_line(f"【{symbol}】\n" + report)
            
            time.sleep(sleep_time)
            
        except Exception as e:
            print(f"🆘 【{symbol} 分隊異常】: {e} | 即將執行精準自癒重啟...")
            update_heartbeat(symbol, "RESTARTING")
            time.sleep(15) 
            continue

def market_scanning_loop(scanner, storage):
    """【市場偵照中心】: 監控全市場機會與磁碟健康"""
    print("🔎 市場偵照雷達啟動中...")
    while True:
        try:
            storage.check_and_cleanup_disk()
            tier = storage.get_performance_tier()
            scan_limit = 10 if tier == "SEED" else (20 if tier == "GROWTH" else 50)
            opportunities = scanner.scan_market(limit=scan_limit)
            storage.save_global_config('RADAR_OPPS', json.dumps([o['symbol'] for o in opportunities]))
            time.sleep(600)
        except Exception: time.sleep(60)

def round_table_loop(storage):
    """【圓桌會議】: 制定全局風險策略"""
    print("🏛️ 圓桌組長會議系統啟動中...")
    import random
    while True:
        try:
            now = datetime.now()
            if now.hour in [0, 6, 12, 18] and now.minute == 0:
                risk_lvl = random.choice([0.5, 0.8, 1.0, 1.2])
                storage.save_global_config("GLOBAL_RISK_MULTIPLIER", str(risk_lvl))
                status_texts = {0.5: "🛡️ 市場極其危險，全城轉為保守防守", 
                                0.8: "⚖️ 市場震盪空間受限，略縮預算", 
                                1.0: "✅ 市場情緒正常，執行 100% 原始預算", 
                                1.2: "🚀 偵測到大行情噴發徵兆，開啟 120% 激進模式"}
                storage.save_global_config("ROUND_TABLE_LOG", f"主席（BTC）會議結論: {status_texts[risk_lvl]}")
                time.sleep(70) 
            time.sleep(30)
        except: time.sleep(60)

def database_shield_loop():
    """【數據庫守護盾】: 每 12 小時備份一次，防止數據丟失"""
    import shutil
    print("🚑 數據庫守護盾已啟動。")
    while True:
        try:
            path = "data/trading.db"
            if os.path.exists(path):
                shutil.copy2(path, "data/trading_shield_backup.db")
                print("🚑 [數據盾] 核心資產備份成功。")
            time.sleep(12 * 3600)
        except: time.sleep(600)

def main():
    try:
        print("⏳ Metropolis 指揮部啟動中...")
        storage_engine = Storage()
        macro, news, fed, pol, tv = MacroScanner(), NewsScanner(), FedScanner(), PoliticalScanner(), TradingViewScanner('BTC/USDT')
        whale = WhaleWatcher('BTC')
        
        # 分隊名單
        MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XAUT/USDT', 'PEPE/USDT']
        SPECIAL_SYMBOL = 'SPECIAL'
        all_syms = MONITOR_SYMBOLS + [SPECIAL_SYMBOL]
        
        # 初始化組長團隊 (使用完整 Symbol 作為 Key)
        chiefs = {sym: ChiefAnalyst(sym, storage_engine) for sym in all_syms}
        
        print(f"📡 正在派遣 {len(all_syms)} 支特工分隊...")
        for sym in all_syms:
            feed = DataFeed(symbol=sym)
            predictor = AdaptiveMLPredictor(storage=storage_engine)
            init_cash = 100.0 if sym == SPECIAL_SYMBOL else 300.0
            trader = PaperTrader(symbol=sym, initial_cash=init_cash, is_pepe=('PEPE' in sym))
            
            threading.Thread(
                target=agent_worker,
                args=(sym, trader, predictor, feed, storage_engine, macro, whale, news, fed, pol, tv, chiefs),
                daemon=True
            ).start()
            time.sleep(1)
        
        # 啟動守護線程
        scanner = DynamicMarketScanner(storage=storage_engine)
        threading.Thread(target=market_scanning_loop, args=(scanner, storage_engine), daemon=True).start()
        threading.Thread(target=round_table_loop, args=(storage_engine,), daemon=True).start()
        
        print("✅ 【Metropolis 旗艦版 | 全系統服役中】")
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
        
    except Exception as e:
        print(f"❌ 系統啟動失敗: {e}")
        time.sleep(10)

if __name__ == "__main__":
    main()
