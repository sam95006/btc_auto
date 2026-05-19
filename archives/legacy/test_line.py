from notifier import send_line
from datetime import datetime

# 測試 LINE 通知內容
test_msg = (
    f"🔔 BTC 機器人通知測試\n"
    f"⏰ 測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    f"✅ 狀態: 系統連線正常\n"
    f"🚀 您將在產生關鍵交易訊號時收到此通知。"
)

print("正在發送測試 LINE 通知...")
send_line(test_msg)
print("發送完畢！請檢查您的 LINE 介面。")