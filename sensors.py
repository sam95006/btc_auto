import requests
import pandas as pd
import os

class MacroScanner:
    def __init__(self):
        # 宏觀情緒改為「恐懼與貪婪指數」 (100% 免費)
        self.fear_greed_url = "https://api.alternative.me/fng/"

    def get_sentiment_score(self):
        try:
            # 抓取全球情緒
            response = requests.get(self.fear_greed_url).json()
            fng_value = int(response['data'][0]['value'])
            
            # 將 0-100 轉化為我們系統用的 0-1
            # 越高代表越貪婪 (看漲信心可稍微修正)
            score = fng_value / 100.0
            print(f"📊 [全球情緒] 恐懼貪婪指數: {fng_value} (Score: {score:.2f})")
            return score
        except:
            return 0.5

class WhaleWatcher:
    def __init__(self, symbol='BTCUSDT'):
        self.symbol = symbol

    def get_whale_move(self, exchange):
        try:
            # 掃描幣安深度圖 (巨鯨大單偵測)
            orderbook = exchange.fetch_order_book(self.symbol, limit=20)
            bids = sum([b[1] for b in orderbook['bids']])
            asks = sum([a[1] for a in orderbook['asks']])
            ratio = bids / asks if asks > 0 else 1.0
            return ratio
        except:
            return 1.0

# 清除舊的 NewsAI，合併到 MacroScanner 中
