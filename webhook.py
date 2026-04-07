from flask import Flask, request, abort
import requests
import json
import os
import ccxt
from storage import Storage
from sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner

app = Flask(__name__)
storage = Storage()
macro = MacroScanner()
fed = FedScanner()
pol = PoliticalScanner()

# LINE Messaging API Keys
CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '')

def reply_message(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    requests.post(url, headers=headers, data=json.dumps(data))

def get_crypto_price(symbol):
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker(symbol)
        return f"💎 {symbol.replace('/USDT', '')}: ${ticker['last']:,.2f}"
    except:
        return f"💎 {symbol}: 目前數據獲取中..."

def get_hot_coins():
    try:
        exchange = ccxt.binance()
        markets = exchange.fetch_tickers()
        # 過濾 USDT 交易對並依據 24 小時漲幅排序
        usdt_pairs = {k: v for k, v in markets.items() if k.endswith('/USDT') and v['percentage'] is not None}
        sorted_pairs = sorted(usdt_pairs.items(), key=lambda x: x[1]['percentage'], reverse=True)
        
        reco = []
        for pair, data in sorted_pairs:
            # 排除一些小市值或有風險的幣種 (簡單用交易量過濾)
            if data['quoteVolume'] > 50000000: # 交易量大於 50M USDT
                reco.append(f"🔥 {pair.replace('/USDT', '')}: 漲幅 {data['percentage']:.2f}% | 價格: ${data['last']:,.4f}")
            if len(reco) >= 3:
                break
        if len(reco) == 0: return "目前市場無明顯動能強勢幣種。"
        return "\n".join(reco)
    except:
        return "🔥 強勢幣種推薦: 數據獲取中..."

@app.route("/", methods=['GET'])
def health_check():
    return "🚀 【BTC 終極獵手：Sovereign Global Macro Edition】 系統運作中！請對接 /callback URL。", 200

@app.route("/callback", methods=['POST'])
def callback():
    try:
        body = request.get_data(as_text=True)
        events = json.loads(body)['events']
        
        for event in events:
            if event['type'] == 'message' and event['message']['type'] == 'text':
                user_msg = event['message']['text'].lower()
                reply_token = event['replyToken']
                
                # --- 報表系列 ---
                if "持倉" in user_msg or "部位" in user_msg:
                    pos = storage.get_active_pos()
                    if not pos:
                        reply_message(reply_token, "📭 目前空倉，系統正在埋伏下一個完美點位。")
                    else:
                        sym, t, ep, qty, th = pos[1], pos[2], pos[3], pos[4], pos[5]
                        reply_message(reply_token, f"🟢 【目前持倉狀態】\n類別: {t}\n數量: {qty:.4f}\n進場點: ${ep:,.2f}\n追蹤高點: ${th:,.2f}")
                
                elif "今日" in user_msg or "一天" in user_msg:
                    pnl, cnt = storage.get_range_summary(1)
                    recent_trades = storage.get_latest_trades(3)
                    trade_str = "\n".join([f"[{tr[0][-5:]}] 進: ${tr[1]:.0f} | 出: ${tr[2]:.0f} | 盈虧: ${tr[3]:.0f}" for tr in recent_trades])
                    reply_message(reply_token, f"📊 【24H 戰情中心】\n已平倉盈虧: ${pnl:,.2f}\n交易次數: {cnt} 次\n\n【最近交易紀錄】\n{trade_str}")
                    
                elif "三天" in user_msg:
                    pnl, cnt = storage.get_range_summary(3)
                    reply_message(reply_token, f"📊 【3天戰情】\n已平倉盈虧: ${pnl:,.2f}\n交易次數: {cnt} 次")
                    
                elif "一週" in user_msg or "一周" in user_msg:
                    pnl, cnt = storage.get_range_summary(7)
                    recent_trades = storage.get_latest_trades(5)
                    trade_str = "\n".join([f"[{tr[0][-5:]}] 進: ${tr[1]:.0f} | 出: ${tr[2]:.0f} | 盈虧: ${tr[3]:.0f}" for tr in recent_trades])
                    reply_message(reply_token, f"📊 【週報 7天戰情】\n已平倉盈虧: ${pnl:,.2f}\n交易次數: {cnt} 次\n\n【最近 5 筆交易】\n{trade_str}")
                    
                elif "一月" in user_msg or "一個月" in user_msg:
                    pnl, cnt = storage.get_range_summary(30)
                    reply_message(reply_token, f"📊 【月報 30天戰情】\n總結盈虧: ${pnl:,.2f}\n交易次數: {cnt} 次")

                elif "總共" in user_msg or "總額" in user_msg:
                    pnl, cnt = storage.get_lifetime_summary()
                    reply_message(reply_token, f"🏦 【歷史總決算】\n生涯累積盈虧: ${pnl:,.2f}\n總發射次數: {cnt} 次")

                # --- 宏觀情報系列 ---
                elif "快報" in user_msg or "行情" in user_msg:
                    fng = macro.get_sentiment_score()
                    fed_s = fed.get_sentiment()
                    pol_s = pol.get_sentiment()
                    
                    tech_str = "科技連動: 強勁 🚀" if macro.get_tech_stock_pulse() > 1.1 else "科技連動: 正常 ⚖️"
                    fed_str = "聯準會: 鴿派 (利多) 🕊️" if fed_s > 0.55 else ("聯準會: 鷹派 (利空) 🦅" if fed_s < 0.45 else "聯準會: 觀望 ⚖️")
                    pol_str = "地緣政治: 樂觀 🌍" if pol_s > 0.55 else ("地緣政治: 緊張 ⚠️" if pol_s < 0.45 else "地緣政治: 平穩 ⚖️")

                    reply_text = (
                        "📡 【全球金融與加密雷達】\n"
                        f"📊 恐懼貪婪指數: {fng*100:.0f}/100\n"
                        f"📌 {tech_str}\n"
                        f"📌 {fed_str}\n"
                        f"📌 {pol_str}\n\n"
                        "=== 📌 核心追蹤資產 ===\n"
                        f"{get_crypto_price('BTC/USDT')}\n"
                        f"{get_crypto_price('ETH/USDT')}\n"
                        f"{get_crypto_price('SOL/USDT')}\n"
                        f"{get_crypto_price('BNB/USDT')}\n"
                        f"{get_crypto_price('XRP/USDT')}\n"
                        f"{get_crypto_price('PEPE/USDT')}\n\n"
                        "=== 🔮 每週AI強勢動能推薦 ===\n"
                        f"{get_hot_coins()}"
                    )
                    reply_message(reply_token, reply_text)
                
                else:
                    reply_message(reply_token, "🤖 收到指令。支援查詢：\n1.「持倉」\n2.「今日/三天/一週/一月/總共」(附帶精確點位與次數)\n3.「快報」(含6大幣種與全球政經分析、本週強勢推薦)")
        
        return "OK", 200
    except Exception as e:
        print(f"Webhook Error: {e}")
        return "Internal Error", 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
