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

def update_heartbeat(symbol, status="OK"):
    AGENT_HEALTH[symbol] = {
        'status': status,
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
            # 1. [自癒檢查] 每次啟動或重啟先對接資料庫恢復狀態
            trader.load_active_position()
            update_heartbeat(symbol, "OK")
            
            # 2. 抓取技術面數據
            df_data = feed.fetch_ohlcv(timeframe='1m', limit=100)
            if not df_data:
                time.sleep(10)
                continue
                
            df_1m = calculate_all(df_data)
            df_15m = calculate_all(feed.fetch_ohlcv(timeframe='15m', limit=50))
            
            current_price = float(df_1m.iloc[-1]['close'])
            storage.save_global_config(f"PRICE_{symbol}", str(current_price))
            
            # 3. [雷達對接] 獲取巨鯨動向
            whale_score = whale.get_whale_move(feed.exchange) if whale else 1.0
            storage.save_global_config(f"WHALE_{symbol}", str(whale_score))
            
            # 4. AI 智能拍板
            ml_prob = predictor.predict(df_1m) if predictor else 0.5
            team_signal, team_conf = chiefs[symbol].make_final_decision(df_1m, df_15m, {
                'ml_prob': ml_prob,
                'whale_score': whale_score
            })
            
            scalper_signal = "HOLD"
            if team_signal == "BUY": scalper_signal = "BUY_SCALP"
            elif team_signal == "SELL": scalper_signal = "SELL_SCALP"

            # 5. 執行引擎 (內建持倉管理)
            context = {
                'rsi': df_1m.iloc[-1].get('RSI', 50),
                'ml_prob': ml_prob,
                'rv': df_1m.iloc[-1].get('RV', 1.0),
                'whale_score': whale_score
            }
            
            report = trader.execute(scalper_signal, "HOLD", current_price, storage=storage, atr=df_1m.iloc[-1].get('ATR', 0), context=context)
            
            if report:
                tag = f"【{symbol.replace('/USDT','')}】"
                send_line(tag + "\n" + report)
            
            update_heartbeat(symbol, "OK")
            time.sleep(30)
            
        except Exception as e:
            print(f"🆘 【{symbol} 分隊異常】: {e} | 即將執行精準自癒重啟...")
            update_heartbeat(symbol, "RESTARTING")
            time.sleep(15) 
            continue

def market_scanning_loop(scanner, storage):
    """
    【全市場偵照中心】: 定期掃描幣安前 20 大幣種，尋找符合條件的標的並公佈在雷達塔。
    """
    print("🔎 市場偵照雷達啟動中...")
    while True:
        try:
            opportunities = scanner.scan_market(limit=20)
            opp_summary = [o['symbol'] for o in opportunities]
            storage.save_global_config('RADAR_OPPS', json.dumps(opp_summary))
            time.sleep(600)
        except Exception as e:
            print(f"⚠️ 雷達掃描故障: {e}")
            time.sleep(60)

def main():
    def async_init():
        try:
            print("⏳ 啟動終極初始化...")
            storage = Storage()
            predictors = {sym: AdaptiveMLPredictor(storage=storage) for sym in MONITOR_SYMBOLS + [PEPE_SYMBOL]}
            
            macro, news, fed, pol = MacroScanner(), NewsScanner(), FedScanner(), PoliticalScanner()
            feed_manager, traders, whales, tv_scanners = {}, {}, {}, {}
            
            total_cash = 10000
            per_cash = total_cash * 0.2
            
            for sym in MONITOR_SYMBOLS + [PEPE_SYMBOL]:
                feed_manager[sym] = DataFeed(symbol=sym)
                traders[sym] = PaperTrader(symbol=sym, initial_cash=per_cash, is_pepe=(sym == PEPE_SYMBOL))
                whales[sym] = WhaleWatcher(symbol=sym.replace('/',''))
                tv_scanners[sym] = TradingViewScanner(symbol=sym)
            
            # 建立特工共識小組
            all_syms = MONITOR_SYMBOLS + [PEPE_SYMBOL]
            chiefs = {sym: ChiefAnalyst(sym, storage) for sym in all_syms}

            # 啟動特工多執行緒（自癒模式）
            for sym in all_syms:
                t = threading.Thread(
                    target=agent_worker, 
                    args=(sym, traders[sym], predictors.get(sym), feed_manager[sym], storage, macro, whales.get(sym), news, fed, pol, tv_scanners.get(sym), chiefs),
                    name=f"Agent-{sym}"
                )
                t.daemon = True
                t.start()
                print(f"✅ {sym} 特工分隊已部署...")
            
            # 啟動雷達掃描
            scanner = DynamicMarketScanner(storage=storage)
            t_scan = threading.Thread(target=market_scanning_loop, args=(scanner, storage))
            t_scan.daemon = True
            t_scan.start()
            
            print("✅ 【全球作戰體系佈防完畢 | 自癒系統在線】")
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
