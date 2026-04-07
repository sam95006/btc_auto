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
            
            # 關鍵字判定
            if user_msg == "今日報表":
                count, total_pnl = storage.get_today_summary()
                trades = storage.get_today_trades()
                
                report = f"📊 今日交易報表 ({datetime.now().strftime('%Y-%m-%d')})\n"
                report += f"------------------\n"
                report += f"✅ 結算次數: {count} 次\n"
                report += f"💰 今日總損益: ${total_pnl:,.2f}\n\n"
                
                if trades:
                    report += "📝 交易明細 (最近 5 筆):\n"
                    for t in trades[-5:]:
                        # t 格式: (type, price, pnl, timestamp)
                        t_type, price, pnl, ts = t
                        time_short = ts.split('T')[1][:5] if 'T' in ts else ""
                        pnl_info = f" | 獲利: ${pnl:,.1f}" if t_type == 'SELL' else ""
                        report += f"• {time_short} {t_type} @ {price:,.0f}{pnl_info}\n"
                else:
                    report += "目前今天尚無成交紀錄。"
                
                reply_line(reply_token, report)
                
    return 'OK'

if __name__ == "__main__":
    print("-" * 30)
    print("LINE Webhook Server 啟動中...")
    print("Port: 5000 | Endpoint: /callback")
    print("-" * 30)
    app.run(port=5000)
