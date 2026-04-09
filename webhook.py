import os
import sys
import json
import logging
import re
from datetime import datetime, timedelta
from flask import Flask, request, abort, render_template, jsonify
from flask_cors import CORS
import requests

# 【路徑環境強化】
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.storage import Storage

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

storage = Storage()

@app.route("/")
def home():
    return "BTC Bot API is running! Access the Metropolis at /village"

@app.route("/village")
def village():
    return render_template("village.html")

@app.route("/api/health")
def api_health():
    """回傳特工自癒系統的健康狀態"""
    return jsonify(getattr(app, 'agent_status', {}))

@app.route("/api/stats")
def api_stats():
    """主 HUD 數據接口: 整合健康、價格、與財務"""
    try:
        total_pnl, _ = storage.get_lifetime_summary()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = storage.conn.cursor()
        cursor.execute("SELECT SUM(pnl) FROM trades WHERE timestamp LIKE ?", (f"{today}%",))
        today_pnl = cursor.fetchone()[0] or 0.0
        
        # 活躍持倉
        cursor.execute("SELECT * FROM active_pos")
        rows = cursor.fetchall()
        positions = []
        for r in rows:
            sym = r['symbol']
            price_key = f"PRICE_{sym}" if '/' in sym else f"PRICE_{sym}/USDT"
            current_p = float(storage.get_global_config(price_key, r['entry_price']))
            pnl = (current_p - r['entry_price']) * r['qty'] if r['type'] == 'LONG' else (r['entry_price'] - current_p) * r['qty']
            positions.append({'symbol': sym, 'pnl': pnl, 'type': r['type'], 'price': current_p})
            
        # --- [大盤觀測系統: 台北 vs 紐約] ---
        now_utc = datetime.utcnow()
        now_tpe = now_utc + timedelta(hours=8)
        now_nyc = now_utc - timedelta(hours=4) # 目前為夏令時間 (EDT)

        def get_market_info(n, open_h, open_m, close_h, close_m):
            curr_min = n.hour * 60 + n.minute
            start_min = open_h * 60 + open_m
            end_min = close_h * 60 + close_m
            
            if n.weekday() >= 5: # 週末
                days_to_mon = 7 - n.weekday()
                rem_min = (days_to_mon * 1440) + start_min - curr_min
                return "休市中 (週末)", f"{rem_min//1440}天 { (rem_min%1440)//60:02d}:{(rem_min%60):02d} 後開盤"
                
            if start_min <= curr_min < end_min: # 盤中
                rem_min = end_min - curr_min
                return "盤中交易中", f"{rem_min//60:02d}:{rem_min%60:02d} 後收盤"
            else: # 盤後或盤前
                if curr_min >= end_min: # 已收盤，計算到明天開盤
                    rem_min = (1440 - curr_min) + start_min
                else: # 盤前
                    rem_min = start_min - curr_min
                return "已收盤", f"{rem_min//60:02d}:{rem_min%60:02d} 後開盤"

        taiex_status, taiex_cd = get_market_info(now_tpe, 9, 0, 13, 30)
        sp500_status, sp500_cd = get_market_info(now_nyc, 9, 30, 16, 0)
        
        # 指數模擬: 隨時間跳動 (真實點數模擬)
        t_base, s_base = 20350, 5210
        taiex_idx = f"{t_base + (now_tpe.second % 30) - 15 + (now_tpe.minute % 10):,.2f}"
        sp500_idx = f"{s_base + (now_nyc.second % 20) - 10 + (now_nyc.minute % 5):,.2f}"

        # --- [圓桌會議分時紀錄] ---
        meeting_slots = ["00:00", "06:00", "12:00", "18:00"]
        meeting_logs = {}
        for slot in meeting_slots:
            log = storage.get_global_config(f"RT_LOG_{slot}", f"主席（BTC）: {slot} 會議結論執行中，全城分隊戰略部署完畢。")
            meeting_logs[slot] = log
        
        # --- [大會戰數據讀取] ---
        prices = {}
        for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PEPE/USDT']:
            p = storage.get_global_config(f"PRICE_{sym}", "0.0")
            prices[sym.split('/')[0]] = p
        
        radar_opps = json.loads(storage.get_global_config('RADAR_OPPS', '[]'))
        whale_score = storage.get_global_config('WHALE_BTC/USDT', '1.0')
        treasury_cash = storage.get_global_config("TREASURY_CASH", "1000.0")
        global_alert = storage.get_global_config("GLOBAL_ALERT", "NORMAL")
        
        debts = {}
        thoughts = {}
        for sym in ['BTC', 'ETH', 'SOL', 'XAUT', 'PEPE', 'SPECIAL']:
            debts[sym] = storage.get_global_config(f"DEBT_{sym}/USDT" if '/' not in sym and sym != 'SPECIAL' else f"DEBT_{sym}", "0.0")
            thoughts[sym] = storage.get_global_config(f"THOUGHT_{sym}/USDT" if '/' not in sym and sym != 'SPECIAL' else f"THOUGHT_{sym}", "正在監控幣安鏈路...")

        meeting_times = ["00:00", "06:00", "12:00", "18:00"]
        meetings = [{"time": mt, "status": ("已完成" if now_tpe.hour >= int(mt.split(':')[0]) else "預計召開")} for mt in meeting_times]

        # --- [燈號心跳] ---
        health_data = {}
        for s in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XAUT/USDT', 'PEPE/USDT', 'SPECIAL']:
            st = storage.get_global_config(f"HEALTH_{s}", "ERR")
            health_data[s] = {"status": "OK" if st == "OK" else "OFFLINE"}
        
        # --- [精準資金校準與精英競賽] ---
        ace_symbol = "BTC"
        max_pnl = -999999
        accounts_data = {}
        for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XAUT/USDT', 'PEPE/USDT']:
            cash = float(storage.get_global_config(f"CASH_{sym}", "300.0"))
            init = 300.0
            debt = float(storage.get_global_config(f"DEBT_{sym}", "0.0"))
            accounts_data[sym] = {"cash": cash, "initial": init, "debt": debt}
            current_pnl = cash - init
            if current_pnl > max_pnl: max_pnl, ace_symbol = current_pnl, sym.split('/')[0]
        
        accounts_data['TREASURY'] = {"cash": float(storage.get_global_config("TREASURY_CASH", "1000.0")), "initial": 1000.0, "debt": 0.0}
        accounts_data['SPECIAL'] = {"cash": float(storage.get_global_config("CASH_SPECIAL", "100.0")), "initial": 100.0, "debt": 0.0}
        
        # 決定日報摘要與最新會議日誌
        debrief_summary = f"🎉 今日由 {ace_symbol} 領跑全城，趨勢捕捉非常精準！" if max_pnl > 10 else "全軍陣勢穩健，各特工正在靜候大行情爆發。"
        last_slot = "00:00"
        for s in ["00:00", "06:00", "12:00", "18:00"]:
            if now_tpe.hour >= int(s.split(':')[0]): last_slot = s
        round_table_log = meeting_logs[last_slot]
        
        return jsonify({
            "tpe_time": now_tpe.strftime("%H:%M:%S"),
            "ny_time": now_nyc.strftime("%H:%M:%S"),
            "taiex_info": {"status": taiex_status, "countdown": taiex_cd, "index": taiex_idx},
            "sp500_info": {"status": sp500_status, "countdown": sp500_cd, "index": sp500_idx},
            "today_pnl": today_pnl,
            "total_pnl": total_pnl,
            "treasury_cash": treasury_cash,
            "global_alert": global_alert,
            "meetings": meetings,
            "meeting_logs": meeting_logs,
            "round_table_log": round_table_log,
            "daily_debrief": debrief_summary,
            "ace_agent": ace_symbol,
            "whale_mvt": storage.get_global_config("WHALE_MVT", "正在掃描大戶錢包流向..."),
            "prices": prices,
            "debts": debts,
            "thoughts": thoughts,
            "agent_health": health_data,
            "positions": positions,
            "radar_opps": radar_opps,
            "whale_score": whale_score,
            "team_accounts": accounts_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/news")
def api_news():
    import xml.etree.ElementTree as ET
    def fetch_rss(query):
        try:
            url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            resp = requests.get(url, timeout=5)
            root = ET.fromstring(resp.content)
            return [item.find('title').text.split(' - ')[0] for item in root.findall('./channel/item')[:10]]
        except: return ["📡 衛星信號對應中..."]

    return jsonify({
        "intl_news": fetch_rss("Finance"),
        "crypto_news": fetch_rss("Bitcoin"),
        "fed_news": fetch_rss("FED"),
        "tv_status": ["BTC: 看漲", "ETH: 看漲", "SOL: 中立"]
    })

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
