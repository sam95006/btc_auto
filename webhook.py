from flask import Flask, request, abort
import os
import requests
from storage import Storage
from datafeed import DataFeed
from indicators import calculate_all

app = Flask(__name__)

# --- LINE 設定 ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

def send_line_reply(reply_token, message):
    url = 'https://api.line.me/v2/bot/message/reply'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    payload = {
        'replyToken': reply_token,
        'messages': [{'type': 'text', 'text': message}]
    }
    requests.post(url, headers=headers, json=payload)

def get_coin_prediction(symbol):
    feed = DataFeed(symbol=symbol)
    try:
        df = calculate_all(feed.fetch_ohlcv(timeframe='1h', limit=100))
        price = df.iloc[-1]['close']
        rsi = df.iloc[-1]['RSI']
        # 簡單趨勢預算 (未來 3 天)
        trend = "📈 看漲 (Bullish)" if rsi < 60 else "📉 調整 (Neutral/Pullback)"
        confidence = "中等" if 40 < rsi < 60 else "高"
        return f"💎 {symbol}: ${price:,.4f}\n🔮 3日預測: {trend}\n🎯 信心度: {confidence}"
    except:
        return f"💎 {symbol}: 目前數據獲取中..."

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    signature = request.headers.get('X-Line-Signature')
    
    events = request.json.get('events', [])
    for event in events:
        if event['type'] == 'message' and event['message']['type'] == 'text':
            user_msg = event['message']['text']
            reply_token = event['replyToken']
            
            storage = Storage()
            report = ""

            if "今日報表" in user_msg:
                pnl, count = storage.get_range_summary(days=1)
                report = f"📊 【今日戰績報告】\n💰 淨損益: ${pnl:,.2f}\n🔄 交易次數: {count} 次\n📅 期別: 24 小時內"
            
            elif "三天報表" in user_msg:
                pnl, count = storage.get_range_summary(days=3)
                report = f"🗓 【三日循環報告】\n💰 淨損益: ${pnl:,.2f}\n🔄 交易次數: {count} 次\n📅 期別: 72 小時內"
                
            elif "一周報表" in user_msg or "一週報表" in user_msg:
                pnl, count = storage.get_range_summary(days=7)
                report = f"週 【週度勝率報告】\n💰 淨損益: ${pnl:,.2f}\n🔄 交易次數: {count} 次\n📅 期別: 7 天內"

            elif "一月報表" in user_msg:
                pnl, count = storage.get_range_summary(days=30)
                report = f"月 【月度累積報告】\n💰 淨損益: ${pnl:,.2f}\n🔄 交易次數: {count} 次\n📅 期別: 30 天內"

            elif "總體報表" in user_msg or "從頭到尾" in user_msg:
                pnl, count = storage.get_lifetime_summary()
                # 初始偏移校正
                final_pnl = pnl - 43.87 # 包含之前的手動記錄
                report = (f"🏆 【全週期：終極結算】\n"
                          f"💰 總淨損益: ${final_pnl:,.2f}\n"
                          f"🔄 總交易次數: {count} 次\n"
                          f"🛡️ 狀態: 24/7 全天候監控中")

            elif "市場快報" in user_msg or "行情" in user_msg:
                eth = get_coin_prediction("ETH/USDT")
                pepe = get_coin_prediction("PEPE/USDT")
                xaut = get_coin_prediction("XAUT/USDT") # 黃金
                report = f"🌍 【全資產市場掃描】\n\n{eth}\n\n{pepe}\n\n{xaut}\n\n⚠️ 注: 預測僅供參考，量化系統專注於 BTC 交易。"

            elif "持倉" in user_msg or "部位" in user_msg:
                active = storage.get_active_pos()
                if active and active[2] != "NONE":
                    symbol = active[1]
                    pos_type = "🟢 多單 (Long)" if active[2] == "LONG" else "🔴 空單 (Short)"
                    entry_price = active[3]
                    qty = active[4]
                    
                    # 抓取即時價格計算浮盈
                    feed = DataFeed(symbol='BTC/USDT')
                    try:
                        df = feed.fetch_ohlcv(timeframe='1m', limit=1)
                        current_price = df.iloc[-1]['close']
                        pnl = (current_price - entry_price) * qty if active[2] == "LONG" else (entry_price - current_price) * qty
                        report = (f"🔍 【即時持倉透視】\n"
                                  f"🔹 方向: {pos_type}\n"
                                  f"🔹 進場價格: ${entry_price:,.2f}\n"
                                  f"🔹 目前現價: ${current_price:,.2f}\n"
                                  f"🔹 倉位大小: {qty:.4f}\n"
                                  f"💰 浮動盈虧: ${pnl:,.2f}")
                    except:
                        report = f"🔍 【持倉資訊】\n進場價: ${entry_price:,.2f}\n方向: {pos_type}\n(即時報價獲取中...)"
                else:
                    report = "🔍 目前空手觀望中，雷達持續掃描進場點 (No Active Positions)。"

            if report:
                send_line_reply(reply_token, report)

    return 'OK'

if __name__ == "__main__":
    app.run(port=5000)
