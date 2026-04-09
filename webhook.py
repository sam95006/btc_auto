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
            
        now = datetime.utcnow()
        tpe = (now + timedelta(hours=8)).strftime("%H:%M")
        ny = (now - timedelta(hours=4)).strftime("%H:%M")
        
        # 獲取幣安即時價格
        prices = {}
        for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PEPE/USDT']:
            p = storage.get_global_config(f"PRICE_{sym}", "0.0")
            prices[sym.split('/')[0]] = p
        
        # 獲取雷達、巨鯨、金庫與債務數據
        radar_opps = json.loads(storage.get_global_config('RADAR_OPPS', '[]'))
        whale_score = storage.get_global_config('WHALE_BTC/USDT', '1.0')
        treasury_cash = storage.get_global_config("TREASURY_CASH", "1000.0")
        
        debts = {}
        for sym in ['BTC', 'ETH', 'SOL', 'XAUT', 'PEPE', 'SPECIAL']:
            debts[sym] = storage.get_global_config(f"DEBT_{sym}/USDT" if '/' not in sym and sym != 'SPECIAL' else f"DEBT_{sym}", "0.0")

        # --- 市場開閉盤邏輯 ---
        now_tpe = now + timedelta(hours=8)
        now_nyc = now - timedelta(hours=4) # 夏令時間
        
        def get_mkt_status(n, open_h, open_m, close_h, close_m, name):
            if n.weekday() >= 5: return "休市中 (週末)", "--:--"
            curr = n.hour * 60 + n.minute
            start = open_h * 60 + open_m
            end = close_h * close_m
            if start <= curr < end:
                rem = end - curr
                return "盤中交易", f"{rem//60:02d}:{rem%60:02d} 後收盤"
            else:
                if curr < start: rem = start - curr
                else: rem = (24*60 - curr) + start
                return "已休市", f"{rem//60:02d}:{rem%60:02d} 後開盤"

        taiex_status, taiex_cd = get_mkt_status(now_tpe, 9, 0, 13, 30, "台股")
        sp500_status, sp500_cd = get_mkt_status(now_nyc, 9, 30, 16, 0, "美股")

        return jsonify({
            "tpe_time": now_tpe.strftime("%H:%M:%S"),
            "ny_time": now_nyc.strftime("%H:%M:%S"),
            "taiex_info": {"status": taiex_status, "countdown": taiex_cd},
            "sp500_info": {"status": sp500_status, "countdown": sp500_cd},
            "today_pnl": today_pnl,
            "total_pnl": total_pnl,
            "meeting_log": "自愈中心：全線子系統正在重新校準，請稍候數據對接...",
            "agent_health": getattr(app, 'agent_status', {}),
            "prices": prices,
            "debts": debts,
            "treasury_cash": treasury_cash,
            "positions": positions,
            "radar_opps": radar_opps,
            "whale_score": whale_score,
            "market_indices": {
                "taiex": {"price": 20450, "change": "+1.2%"},
                "sp500": {"price": 5205, "change": "+0.4%"}
            }
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
