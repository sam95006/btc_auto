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
            # 1. [自癒檢查] 對接資料庫並恢復狀態
            trader.load_active_position()
            
            # --- [能量守護 & 全球情緒感知] ---
            ohlcv_raw = feed.fetch_ohlcv(timeframe='1m', limit=100)
            if not ohlcv_raw:
                time.sleep(10)
                continue
            
            import pandas as pd
            df_data = pd.DataFrame(ohlcv_raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # A. 波動率判定 (Eco-Mode)
            range_pct = (df_data['high'].iloc[-5:].max() - df_data['low'].iloc[-5:].min()) / df_data['close'].iloc[-1]
            if range_pct < 0.002:
                sleep_time, mode = 120, "ECO"
            else:
                sleep_time, mode = 30, "BATTLE"

            # B. 巨鯨警戒判定
            whale_score = whale.get_whale_move(feed.exchange) if whale else 1.0
            storage.save_global_config(f"WHALE_{symbol}", str(whale_score))
            if whale_score > 3.5:
                storage.save_global_config("GLOBAL_ALERT", "RED")
            
            update_heartbeat(symbol, "OK", mode)
            
            df_1m = calculate_all(df_data)
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            current_price = float(df_1m.iloc[-1]['close'])
            storage.save_global_config(f"PRICE_{symbol}", str(current_price))
            
            # C. AI 決策與執行
            ml_prob = predictor.predict(df_1m) if predictor else 0.5
            team_signal, team_conf = chiefs[symbol].make_final_decision(df_1m, df_15m, {
                'ml_prob': ml_prob,
                'whale_score': whale_score
            })
            
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
    【圓桌組長會議】: 每日 4 次 (00, 06, 12, 18 點)
    各分隊組長互相交換心得，產出全城共識報告。
    """
    print("🏛️ 圓桌組長會議系統已就緒。")
    import random
    while True:
        try:
            now = datetime.now()
            # 檢查是否到開會時間 (整點)
            if now.hour in [0, 6, 12, 18] and now.minute == 0:
                print(f"🏛️ 【全城通報】圓桌組長會議正在召開 (時間: {now.hour}:00)...")
                
                # 收集各分隊最後的想法
                thoughts = []
                for sym in ['BTC', 'ETH', 'SOL', 'XAUT', 'PEPE']:
                    t = storage.get_global_config(f"THOUGHT_{sym}/USDT", "正在觀察行情...")
                    thoughts.append(f"{sym}: {t}")
                
                # 基於所有特工的想法產生一份共識 (模擬 AI 互相學習)
                base_logs = [
                    "主席（BTC）: 目前各分隊紀律良好，巨鯨動向稍有放緩，維持合約槓桿制約。",
                    "主席（BTC）: 注意近期非農數據影響，黃金分隊（XAUT）需加大避險敏感度。",
                    "主席（BTC）: 今日掃描發現小幣波動劇烈，雷達特別隊需謹慎出擊。",
                    "主席（BTC）: 整體系統持倉穩定，各組長交換的心得顯示技術指標目前具備高度一致性。"
                ]
                final_log = random.choice(base_logs) + " (共識摘要: " + " | ".join(thoughts[:3]) + ")"
                
                storage.save_global_config("ROUND_TABLE_LOG", final_log)
                time.sleep(70) # 避開重複整點觸發
            
            time.sleep(30)
        except Exception as e:
            time.sleep(60)

def main():
    def async_init():
        try:
            print("⏳ 啟動大改革初始化任務...")
            storage = Storage()
            
            # --- [金融改革] 資金分配初始化 ---
            MONITOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XAUT/USDT']
            PEPE_SYMBOL = 'PEPE/USDT'
            SPECIAL_SYMBOL = 'SPECIAL'
            
            storage.save_global_config("TREASURY_CASH", "1000.0")
            
            all_target_syms = MONITOR_SYMBOLS + [PEPE_SYMBOL]
            
            predictors = {sym: AdaptiveMLPredictor(storage=storage) for sym in all_target_syms + [SPECIAL_SYMBOL]}
            macro, news, fed, pol = MacroScanner(), NewsScanner(), FedScanner(), PoliticalScanner()
            feed_manager, traders, whales, tv_scanners = {}, {}, {}, {}
            
            # 1. 初始化核心分隊 (每隊 300U)
            for sym in all_target_syms:
                feed_manager[sym] = DataFeed(symbol=sym)
                traders[sym] = PaperTrader(symbol=sym, initial_cash=300.0, is_pepe=(sym == PEPE_SYMBOL))
                whales[sym] = WhaleWatcher(symbol=sym.replace('/',''))
                tv_scanners[sym] = TradingViewScanner(symbol=sym)
            
            # 2. 初始化特別資金分隊 (100U)
            traders[SPECIAL_SYMBOL] = PaperTrader(symbol=SPECIAL_SYMBOL, initial_cash=100.0)
            whales[SPECIAL_SYMBOL] = WhaleWatcher(symbol="BTC") 
            
            chiefs = {sym: ChiefAnalyst(sym, storage) for sym in all_target_syms + [SPECIAL_SYMBOL]}

            # 3. 部署所有特工指令
            for sym in all_target_syms + [SPECIAL_SYMBOL]:
                target_feed = feed_manager.get(sym, feed_manager['BTC/USDT'])
                t = threading.Thread(
                    target=agent_worker, 
                    args=(sym, traders[sym], predictors.get(sym), target_feed, storage, macro, whales.get(sym), news, fed, pol, tv_scanners.get(sym), chiefs),
                    name=f"Agent-{sym}"
                )
                t.daemon = True
                t.start()
            
            # 啟動雷達掃描與圓桌會議
            scanner = DynamicMarketScanner(storage=storage)
            threading.Thread(target=market_scanning_loop, args=(scanner, storage), daemon=True).start()
            threading.Thread(target=round_table_loop, args=(storage,), daemon=True).start()
            
            print("✅ 【大都會 v5.0 部署完畢 | 圓桌會議在線】")
        except Exception as e:
            print(f"❌ 初始化崩潰: {e}")

    init_t = threading.Thread(target=async_init)
    init_t.daemon = True
    init_t.start()

    try:
        port = int(os.environ.get('PORT', 8080))
        webhook_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"❌ 系統啟動失敗: {e}")

if __name__ == "__main__":
    main()
