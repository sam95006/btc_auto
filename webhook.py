from flask import Flask, request, abort
from storage import Storage
from notifier import TOKEN
import requests
import json
from datetime import datetime

app = Flask(__name__)
storage = Storage()

def reply_line(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TOKEN}"
    }
    data = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    requests.post(url, headers=headers, data=json.dumps(data))

@app.route("/")
def home():
    # Render 健康檢查端點
    return "BTC Bot is Online and Operating 24/7!"

@app.route("/callback", methods=['POST'])
def callback():
    # 接收 LINE Webhook 訊息
    body = request.get_data(as_text=True)
    try:
        payload = json.loads(body)
    except:
        return 'OK'
    
    for event in payload.get('events', []):
        # 僅處理文字訊息
        if event['type'] == 'message' and event['message']['type'] == 'text':
            user_msg = event['message']['text'].strip()
            reply_token = event['replyToken']
            
            # 關鍵字判定與強健回傳
            user_text = user_msg
            title = ""
            
            try:
                if "今日報表" in user_text:
                    count, pnl = storage.get_today_summary()
                    title = "📊 今日交易報表"
                elif "三天報表" in user_text:
                    count, pnl = storage.get_range_summary(days=3)
                    title = "📉 三天累積報表"
                elif "本週報表" in user_text:
                    count, pnl = storage.get_range_summary(days=7)
                    title = "📅 本週累積報表"
                elif "本月報表" in user_text:
                    count, pnl = storage.get_range_summary(days=30)
                    title = "🗓️ 本月累積報表"
                elif "總體報表" in user_text:
                    count, pnl = storage.get_total_summary()
                    title = "📈 全球總結算報表"
                
                if title:
                    initial_capital = 10000.0
                    current_balance = initial_capital + pnl - 43.87
                    report = (f"{title}\n"
                             f"------------------\n"
                             f"✅ 結算次數: {count} 次\n"
                             f"💰 累積損益: ${pnl:,.2f}\n"
                             f"🏦 目前餘額: ${current_balance:,.2f}\n"
                             f"🤖 運作環境: Render AI Cloud")
                    reply_line(reply_token, report)
            except Exception as e:
                reply_line(reply_token, f"⚠️ 報表結算發生意外: {e}")
                
    return 'OK'

if __name__ == "__main__":
    print("-" * 30)
    # LINE 機器人金鑰 (使用安全容逃機制)
    TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
    SECRET = os.environ.get('LINE_CHANNEL_SECRET', '')

    try:
        if TOKEN and SECRET:
            line_bot_api = LineBotApi(TOKEN)
            handler = WebhookHandler(SECRET)
            print("✅ LINE API 連線模組載入成功。")
        else:
            line_bot_api = None
            handler = None
            print("⚠️ 警告: 金鑰尚未設定，LINE 通知功能將暫時關閉。")
    except Exception as e:
        line_bot_api = None
        handler = None
        print(f"❌ LINE 初始化失敗: {e}")
    print("Port: 5000 | Endpoint: /callback")
    print("-" * 30)
    app.run(port=5000)
