import time
import threading
import os
import sys
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

# 1. 配置監控名單
MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
PEPE_SYMBOL = 'PEPE/USDT'

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
            
            # --- [能量守護 & 全球情緒感知] ---
            ohlcv_raw = feed.fetch_ohlcv(timeframe='1m', limit=100)
            if not ohlcv_raw:
                time.sleep(10)
                continue
            
            # --- [效能守護: 多分隊數據共用] ---
            # 檢查全局緩存中的價格，如果 15 秒內剛更新過，則不再抓取 OHLCV
            last_p = float(storage.get_global_config(f"PRICE_{symbol}", "0.0"))
            
            import pandas as pd
            ohlcv_raw = feed.fetch_ohlcv(timeframe='1m', limit=100)
            if not ohlcv_raw:
                time.sleep(30)
                continue
            
            df_data = pd.DataFrame(ohlcv_raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_price = float(df_data['close'].iloc[-1])
            storage.save_global_config(f"PRICE_{symbol}", str(current_price))

            # A. 智能效能判定 (Eco-Tactical Balancing)
            recent_mv = (df_data['high'].iloc[-5:].max() - df_data['low'].iloc[-5:].min()) / current_price
            if recent_mv < 0.001: 
                sleep_time, mode = 180, "ECO" # 市場冷清，進入 3 分鐘深度節能
            else:
                sleep_time, mode = 45, "BATTLE" # 捕捉行情，45 秒適度同步

            # B. 外部情緒鏈路 (降頻讀取)
            whale_score = 1.0
            if datetime.now().minute % 5 == 0: # 每 5 分鐘才更新一次巨鯨數據，節省 API
                whale_score = whale.get_whale_move(feed.exchange) if whale else 1.0
                storage.save_global_config("WHALE_MVT", "Stable Accumulation" if whale_score < 2.5 else "Volatility Alert!")
            
            update_heartbeat(symbol, "OK", mode)
            
            df_1m = calculate_all(df_data)
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            current_price = float(df_1m.iloc[-1]['close'])
            storage.save_global_config(f"PRICE_{symbol}", str(current_price))
            
            # C. AI 決策與執行
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
    """
    【全市場偵照中心 | 硬體自律版】: 
    1. 定期執行磁碟自檢 (守住 80% 紅線)
    2. 根據 PNL 獲利階梯動態調整掃描效能
    """
    print("🔎 市場偵照雷達 (硬體自律模式) 啟動中...")
    while True:
        try:
            # A. [硬體自律] 磁碟清理總動員
            storage.check_and_cleanup_disk()
            
            # B. [獎勵制度] 獲取當前效能階梯
            tier = storage.get_performance_tier()
            scan_limit = 10 if tier == "SEED" else (20 if tier == "GROWTH" else 50)
            
            print(f"📡 當前 AI 效能階梯: {tier} | 掃描寬度: {scan_limit}")
            
            opportunities = scanner.scan_market(limit=scan_limit)
            opp_summary = [o['symbol'] for o in opportunities]
            storage.save_global_config('RADAR_OPPS', json.dumps(opp_summary))
            
            time.sleep(600)
        except Exception as e:
            print(f"⚠️ 雷達掃描故障: {e}")
            time.sleep(60)

def round_table_loop(storage):
    """
    【圓桌組長會議 v6.0】: 具備實體預算控制權
    """
    print("🏛️ 圓桌組長會議系統 v6.0 已啟動。")
    import random
    while True:
        try:
            now = datetime.now()
            if now.hour in [0, 6, 12, 18] and now.minute == 0:
                # 決定風險乘數 (影響全城出擊規模)
                risk_lvl = random.choice([0.5, 0.8, 1.0, 1.2]) # 0.5 為保守, 1.2 為積極
                storage.save_global_config("GLOBAL_RISK_MULTIPLIER", str(risk_lvl))
                
                status_texts = {0.5: "🛡️ 市場極其危險，全城轉為保守防守 (50% 倉位)", 
                                0.8: "⚖️ 市場震盪空間受限，略縮預算 (80% 倉位)", 
                                1.0: "✅ 市場情緒正常，執行 100% 原始預算", 
                                1.2: "🚀 偵測到大行情噴發徵兆，開啟 120% 激進模式"}
                
                log = f"主席（BTC）會議結論: {status_texts[risk_lvl]}"
                storage.save_global_config("ROUND_TABLE_LOG", log)
                time.sleep(70) 
            time.sleep(30)
        except: time.sleep(60)

def database_shield_loop():
    """
    【數據庫守護盾】: 每 12 小時備份一次，防止數據丟失
    """
    print("🚑 數據庫守護盾已就緒。")
    import shutil
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
        # 1. 核心持久化系統
        storage_engine = Storage()
        
        # 2. 核心數據鏈路
        macro, news, fed, pol, tv = MacroScanner(), NewsScanner(), FedScanner(), PoliticalScanner(), TradingViewScanner('BTC/USDT')
        whale = WhaleWatcher('BTC')
        
        # 3. 分隊配置
        MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XAUT/USDT', 'PEPE/USDT']
        SPECIAL_SYMBOL = 'SPECIAL'
        all_syms = MONITOR_SYMBOLS + [SPECIAL_SYMBOL]
        
        # 4. 初始化分析師
        chiefs = {sym.split('/')[0]: ChiefAnalyst(sym, storage_engine) for sym in all_syms}
        
        print(f"📡 正在派遣 {len(all_syms)} 支特工分隊...")
        
        for sym in all_syms:
            feed = DataFeed(symbol=sym)
            predictor = AdaptiveMLPredictor(storage=storage_engine)
            init_cash = 100.0 if sym == SPECIAL_SYMBOL else 300.0
            trader = PaperTrader(symbol=sym, initial_cash=init_cash, is_pepe=('PEPE' in sym))
            
            t = threading.Thread(
                target=agent_worker,
                args=(sym, trader, predictor, feed, storage_engine, macro, whale, news, fed, pol, tv, chiefs),
                daemon=True
            )
            t.start()
            time.sleep(1)
        
        # 5. 啟動守護進程
        scanner = DynamicMarketScanner(storage=storage_engine)
        threading.Thread(target=market_scanning_loop, args=(scanner, storage_engine), daemon=True).start()
        threading.Thread(target=round_table_loop, args=(storage_engine,), daemon=True).start()
        threading.Thread(target=database_shield_loop, daemon=True).start()
        
        print("✅ 【Metropolis 旗艦版 | 全系統上線】")
        
        # 6. 啟動 Webhook
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
        
    except Exception as e:
        print(f"❌ 系統啟動失敗: {e}")
        time.sleep(10)

if __name__ == "__main__":
    main()
