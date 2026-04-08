import os
import ccxt
import pandas as pd
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from sensors import MacroScanner, FedScanner, PoliticalScanner
import logging
from storage import Storage

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 配置 LINE
# 取得 LINE Bot 必要的環境變數，若未設定則直接退出並記錄錯誤
LINE_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_SECRET = os.getenv('LINE_CHANNEL_SECRET')
if not LINE_TOKEN or not LINE_SECRET:
    logging.error('缺少 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 環境變數，服務無法啟動')
    raise SystemExit('環境變數未設定，請在 Zeabur 設定頁面加入')
line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

storage = Storage()
macro = MacroScanner()
fed = FedScanner()
pol = PoliticalScanner()

# 監控名單
MONITOR_LIST = ['BTC', 'ETH', 'SOL', 'PEPE']

def reply_message(token, text):
    line_bot_api.reply_message(token, TextSendMessage(text=text))

def help_message():
    return "可用指令:\n1. 持倉/部位 - 查看當前持倉\n2. 今日/一天 - 查看24小時報表\n3. 快報/行情 - 查看全球金融雷達\n請輸入關鍵字以獲取相應資訊。"

@app.route("/")
def home():
    return "BTC Bot is running!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    reply_token = event.reply_token

    try:
        # --- 權威戰報系統 ---
        if "持倉" in user_msg or "部位" in user_msg:
            all_pos = storage.get_all_active_pos()
            pos_map = {p[1]: p for p in all_pos} # 依照幣種索引
            
            report = "🟢 【當前多路軍團持倉狀態】\n"
            for sym in MONITOR_LIST:
                if sym in pos_map:
                    p = pos_map[sym]
                    report += f"\n🪙 {sym}: 已持倉\n進場: ${p[3]:,.2f} | 規模: {p[3]*p[4]:,.1f} U\n"
                else:
                    report += f"\n🪙 {sym}: 📭 目前空倉埋伏中..."
            reply_message(reply_token, report)

        elif "今日" in user_msg or "一天" in user_msg:
            report = "📊 【24H 四軍聯合作戰中心】\n"
            grand_pnl = 0
            
            for sym in MONITOR_LIST:
                detail = storage.get_detailed_stats(1, symbol=sym)
                pnl = detail['total_pnl']
                grand_pnl += pnl
                report += (f"\n🔥 {sym} 戰況:\n"
                           f"已平倉: {pnl:+.1f} U | 出戰 {sum([detail['long_win'], detail['long_loss'], detail['short_win'], detail['short_loss']])} 次\n"
                           f"多單 {detail['long_win']}勝 {detail['long_loss']}敗 | 空單 {detail['short_win']}勝 {detail['short_loss']}敗\n")
            
            total_remained = 10000 + grand_pnl
            report += f"\n💰 【全局總計】\n累計總盈虧: {grand_pnl:+.2f} U\n🏦 總資產估值: {total_remained:,.2f} U"
            reply_message(reply_token, report)

        elif "快報" in user_msg or "行情" in user_msg:
            fng = macro.get_sentiment_score()
            fed_s = fed.get_sentiment()
            pol_s = pol.get_sentiment()
            report = (f"📡 【全球金融雷達】\n"
                      f"📊 恐懼貪婪: {fng*100:.0f}/100\n"
                      f"🕊️ 聯準會感測: {fed_s:.2f} (鴿 > 0.5)\n"
                      f"🌍 地緣政治感測: {pol_s:.2f}\n"
                      "⚡ 市場動能正常，獵手待命中。")
            reply_message(reply_token, report)

        # 若未匹配任何指令，回覆說明訊息
        else:
            reply_message(reply_token, help_message())
    except Exception as e:
        print(f"Webhook 報表錯誤: {e}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
