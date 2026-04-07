import requests
import pandas as pd
import os
import feedparser

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

class NewsScanner:
    def __init__(self):
        # 使用 Google News Bitcoin RSS (免費且免 Key)
        self.rss_url = "https://news.google.com/rss/search?q=bitcoin+crypto+when:1h&hl=en-US&gl=US&ceid=US:en"
        self.bull_keywords = ['etf', 'adoption', 'surge', 'bull', 'gain', 'buy', 'pump', 'growth', 'record', 'safe']
        self.bear_keywords = ['hack', 'crash', 'dump', 'fud', 'scam', 'crackdown', 'regulation', 'sell', 'drop', 'ban']

    def fetch_latest_sentiment(self):
        try:
            feed = feedparser.parse(self.rss_url)
            total_score = 0
            count = 0
            headlines = []
            
            for entry in feed.entries[:10]: # 檢查最近 10 則新聞
                title = entry.title.lower()
                headlines.append(entry.title)
                
                # 簡單關鍵字情緒評分
                score = 0
                for word in self.bull_keywords:
                    if word in title: score += 1
                for word in self.bear_keywords:
                    if word in title: score -= 1
                
                total_score += score
                count += 1
            
            # 歸一化分數為 -1 到 1，然後轉為 0-1 的信心係數
            avg_score = (total_score / count) if count > 0 else 0
            sentiment_final = 0.5 + (avg_score * 0.1) # 略微影響，防止新聞雜訊過大
            sentiment_final = max(0, min(1, sentiment_final))
            
            print(f"📰 [新聞情緒] 掃描最近 {count} 則新聞。初步信心係數: {sentiment_final:.2f}")
            # print(f"最新標題: {headlines[0][:50]}...")
            return sentiment_final
        except Exception as e:
            print(f"❌ 新聞掃描出錯: {e}")
            return 0.5
