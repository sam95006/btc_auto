from flask import Flask, request, abort
import os
import requests
from storage import Storage
from datafeed import DataFeed
from indicators import calculate_all
from sensors import NewsScanner, MacroScanner

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
    try:
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
                
                elif "市場快報" in user_msg or "行情" in user_msg:
                    # 抓取幣種預測
                    eth = get_coin_prediction("ETH/USDT")
                    pepe = get_coin_prediction("PEPE/USDT")
                    xaut = get_coin_prediction("XAUT/USDT")
                    
                    # 抓取即時新聞與全球情緒
                    news = NewsScanner()
                    macro = MacroScanner()
                    news_score = news.fetch_latest_sentiment()
                    fng_score = macro.get_sentiment_score()
                    
                    fng_text = "😱 恐懼" if fng_score < 0.4 else "🤩 貪婪" if fng_score > 0.6 else "😐 中性"
                    news_text = "🔥 利多頻傳" if news_score > 0.6 else "❄️ 情緒低迷" if news_score < 0.4 else "☁️ 消息平淡"
                    
                    report = (f"🌍 【全資產市場大數據】\n\n"
                              f"📰 新聞現狀: {news_text} ({news_score:.2f})\n"
                              f"🧠 全球情緒: {fng_text} ({int(fng_score*100)})\n"
                              f"------------------\n"
                              f"{eth}\n\n"
                              f"{pepe}\n\n"
                              f"{xaut}\n\n"
                              f"⚠️ 注: 內部 AI 已根據此數據自動調整 BTC 交易強度。")

                elif "持倉" in user_msg:
                    active = storage.get_active_pos()
                    if active and active[2] != "NONE":
                        entry_price = active[3]; qty = active[4]
                        feed = DataFeed(symbol='BTC/USDT')
                        df = feed.fetch_ohlcv(timeframe='1m', limit=1)
                        current_price = df.iloc[-1]['close']
                        pnl = (current_price - entry_price) * qty if active[2] == "LONG" else (entry_price - current_price) * qty
                        report = (f"🔍 【即時持倉】\n🔹 方向: {active[2]}\n🔹 進場: ${entry_price:,.2f}\n"
                                  f"🔹 現價: ${current_price:,.2f}\n💰 浮盈: ${pnl:,.2f}")
                    else:
                        report = "🔍 目前空手，雷達掃描中。"

                if report:
                    send_line_reply(reply_token, report)
    except:
        pass
    return 'OK'

if __name__ == "__main__":
    app.run(port=5000)
