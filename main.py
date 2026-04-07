import time
import threading
from datafeed import DataFeed
from indicators import calculate_all
from strategy import check_signal
from execution import PaperTrader
from storage import Storage
from notifier import send_line
from webhook import app as webhook_app  # 導入剛剛建立的 Webhook 伺服器
from datetime import datetime

def run_webhook():
    # 讓 Webhook 跑在背景，Port 8080 適合雲端環境
    print("啟動 Webhook 服務監聽 (Port 8080)...")
    webhook_app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

def main():
    feed = DataFeed(symbol='BTC/USDT')
    storage = Storage()
    
    # 啟動時從資料庫讀取之前的累計損益
    last_pnl = storage.get_last_summary()
    trader = PaperTrader(initial_cumulative_pnl=last_pnl)
    
    print("-" * 40)
    print("BTCUSDT 模擬交易系統啟動 (雲端整合版)")
    print(f"啟動時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"繼承歷史損益: ${last_pnl:,.2f}")
    print("-" * 40)

    # 🚀 在新執行緒 (Thread) 中跑 LINE Webhook
    web_thread = threading.Thread(target=run_webhook)
    web_thread.daemon = True
    web_thread.start()

    while True:
        try:
            # 1. 抓取 Binance 1m 資料
            df = feed.fetch_ohlcv(limit=100)
            
            # 2. 計算指標 (MA20, RSI, MACD)
            df = calculate_all(df)
            latest = df.iloc[-1]
            price = latest['close']
            
            # 3. 檢查策略訊號
            signal = check_signal(df)
            
            # 記錄訊號與指標狀態至 SQLite
            storage.log_signal(signal, price, latest['RSI'], latest['MACD'])
            
            # 4. 模擬執行與交易通知
            trade_report = trader.execute(signal, price, storage)
            
            if trade_report:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {trade_report}")
                send_line(trade_report)
            else:
                # 靜默執行，每分鐘印一條行情日誌
                rpt_line = (f"[{datetime.now().strftime('%H:%M:%S')}] "
                            f"Price: ${price:,.2f} | RSI: {latest['RSI']:.2f} | "
                            f"Signal: {signal}")
                print(rpt_line)
            
            # 5. 每 60 秒執行一次
            time.sleep(60)
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 循環出錯: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
