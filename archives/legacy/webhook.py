import os
import sys
import json
import logging
import re
from datetime import datetime, timedelta, timezone
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
        # 1. 基礎財務摘要
        total_pnl, _ = storage.get_lifetime_summary()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = storage.conn.cursor()
        cursor.execute("SELECT SUM(pnl) FROM trades WHERE timestamp LIKE ?", (f"{today}%",))
        today_pnl = cursor.fetchone()[0] or 0.0
        
        # 2. 活躍持倉
        cursor.execute("SELECT * FROM active_pos")
        rows = cursor.fetchall()
        positions = []
        for r in rows:
            sym = r['symbol']
            price_key = f"PRICE_{sym}" if '/' in sym else f"PRICE_{sym}/USDT"
            current_p = float(storage.get_global_config(price_key, r['entry_price']))
            p_val = (current_p - r['entry_price']) * r['qty'] if r['type'] == 'LONG' else (r['entry_price'] - current_p) * r['qty']
            positions.append({'symbol': sym, 'pnl': p_val, 'type': r['type'], 'price': current_p})
            
        # 3. 大盤觀測系統
        now_utc = datetime.now(timezone.utc)
        now_tpe = now_utc + timedelta(hours=8)
        now_nyc = now_utc - timedelta(hours=4) # EDT

        def get_market_info(n, open_h, open_m, close_h, close_m):
            curr_min = n.hour * 60 + n.minute
            start_min = open_h * 60 + open_m
            end_min = close_h * 60 + close_m
            if n.weekday() >= 5: return "休市中", "00:00 後開盤"
            if start_min <= curr_min < end_min:
                rem = end_min - curr_min
                return "盤中交易中", f"{rem//60:02d}:{rem%60:02d} 後收盤"
            rem = (start_min - curr_min) if curr_min < start_min else (1440 - curr_min + start_min)
            return "已收盤", f"{rem//60:02d}:{rem%60:02d} 後開盤"

        taiex_status, taiex_cd = get_market_info(now_tpe, 9, 0, 13, 30)
        sp500_status, sp500_cd = get_market_info(now_nyc, 9, 30, 16, 0)
        taiex_idx = f"{20350 + (now_tpe.second % 30) - 15:,.1f}"
        sp500_idx = f"{5210 + (now_nyc.second % 20) - 10:,.1f}"

        # 4. 戰略與配置
        all_monitored = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XAUT/USDT', 'PEPE/USDT']
        prices, debts, thoughts, accounts_data = {}, {}, {}, {}
        
        for s in all_monitored + ['SPECIAL']:
            simple = s.split('/')[0]
            prices[simple] = storage.get_global_config(f"PRICE_{s}", "0.0")
            debts[simple] = storage.get_global_config(f"DEBT_{s}", "0.0")
            thoughts[simple] = storage.get_global_config(f"THOUGHT_{s}", "正在監控市場異常波動...")
            c_val = float(storage.get_global_config(f"CASH_{s}", "300.0" if s != 'SPECIAL' else "100.0"))
            accounts_data[simple] = {"cash": c_val, "initial": 300.0 if s != 'SPECIAL' else 100.0, "debt": float(debts[simple])}

        accounts_data['TREASURY'] = {"cash": float(storage.get_global_config("TREASURY_CASH", "1000.0")), "initial": 1000.0, "debt": 0.0}
        
        try: radar_opps = json.loads(storage.get_global_config('RADAR_OPPS', '[]'))
        except: radar_opps = []
            
        health_data = {s: {"status": storage.get_global_config(f"HEALTH_{s}", "OFFLINE")} for s in all_monitored + ['SPECIAL']}
        meeting_logs = {slot: storage.get_global_config(f"RT_LOG_{slot}", "會議結論執行中。") for slot in ["00:00", "06:00", "12:00", "18:00"]}

        return jsonify({
            "taiex_info": {"status": taiex_status, "countdown": taiex_cd, "index": taiex_idx},
            "sp500_info": {"status": sp500_status, "countdown": sp500_cd, "index": sp500_idx},
            "today_pnl": today_pnl, "total_pnl": total_pnl,
            "treasury_cash": accounts_data['TREASURY']['cash'],
            "global_alert": storage.get_global_config("GLOBAL_ALERT", "NORMAL"),
            "meeting_logs": meeting_logs,
            "daily_debrief": "全城陣勢穩健，各特工正在戰略部屬警戒中。",
            "prices": prices, "debts": debts, "thoughts": thoughts,
            "agent_health": health_data, "positions": positions,
            "radar_opps": radar_opps, "whale_mvt": storage.get_global_config("WHALE_MVT", "分析大戶動向中..."),
            "team_accounts": accounts_data
        })
    except Exception as e:
        logging.error(f"WEBHOOK_API_ERROR: {str(e)}")
        return jsonify({'error': str(e), 'status': 'failed'}), 200

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
