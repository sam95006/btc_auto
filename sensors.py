import requests
import pandas as pd
import os
import feedparser

class MacroScanner:
    def __init__(self):
        # 1. 恐懼與貪婪指數 (全球幣圈心跳)
        self.fear_greed_url = "https://api.alternative.me/fng/"
        # 2. NVIDIA (輝達) & NASDAQ 即時情報 (美股領先指標)
        # 使用 Yahoo Finance RSS 作為免費數據源
        self.nvda_rss = "https://finance.yahoo.com/rss/headline?s=NVDA"

    def get_sentiment_score(self):
        try:
            response = requests.get(self.fear_greed_url).json()
            fng_value = int(response['data'][0]['value'])
            return fng_value / 100.0
        except:
            return 0.5

    def get_tech_stock_pulse(self):
        # 掃描 NVIDIA 與美股科技板塊情緒
        try:
            feed = feedparser.parse(self.nvda_rss)
            bullish_keywords = ['surge', 'growth', 'buy', 'up', 'beat', 'rally', 'ai', 'gain']
            score = 0
            for entry in feed.entries[:5]: # 掃描前 5 則 NVDA 重大新聞
                title = entry.title.lower()
                for word in bullish_keywords:
                    if word in title: score += 1
            
            # 科技連動係數 (1.0 代表正常，高於 1.0 代表美股助攻)
            pulse = 1.0 + (score * 0.05) 
            print(f"📡 [美股科技連動] NVDA 情緒加成: {pulse:.2f}x")
            return min(1.3, pulse)
        except:
            return 1.0

class WhaleWatcher:
    def __init__(self, symbol='BTCUSDT'):
        self.symbol = symbol

    def get_whale_move(self, exchange):
        try:
            orderbook = exchange.fetch_order_book(self.symbol, limit=20)
            bids = sum([b[1] for b in orderbook['bids']])
            asks = sum([a[1] for a in orderbook['asks']])
            ratio = bids / asks if asks > 0 else 1.0
            return ratio
        except:
            return 1.0

class NewsScanner:
    def __init__(self):
        self.rss_url = "https://news.google.com/rss/search?q=bitcoin+crypto+when:1h&hl=en-US&gl=US&ceid=US:en"
        self.bull_keywords = ['etf', 'adoption', 'surge', 'bull', 'gain', 'buy', 'pump', 'growth', 'record', 'safe']
        self.bear_keywords = ['hack', 'crash', 'dump', 'fud', 'scam', 'crackdown', 'regulation', 'sell', 'drop', 'ban']

    def fetch_latest_sentiment(self):
        try:
            feed = feedparser.parse(self.rss_url)
            total_score = 0
            count = 0
            for entry in feed.entries[:10]:
                title = entry.title.lower()
                score = 0
                for word in self.bull_keywords:
                    if word in title: score += 1
                for word in self.bear_keywords:
                    if word in title: score -= 1
                total_score += score
                count += 1
            avg_score = (total_score / count) if count > 0 else 0
            sentiment_final = 0.5 + (avg_score * 0.1)
            return max(0, min(1, sentiment_final))
        except:
            return 0.5
