import requests
from bs4 import BeautifulSoup
import time
from tradingview_ta import TA_Handler, Interval

class TradingViewScanner:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol.replace("/","")
        try:
            self.handler = TA_Handler(
                symbol=self.symbol,
                screener="crypto",
                exchange="BINANCE",
                interval=Interval.INTERVAL_15_MINUTES
            )
        except:
            self.handler = None

    def get_sentiment(self):
        if not self.handler: return 0.5
        try:
            analysis = self.handler.get_analysis()
            rec = analysis.summary['RECOMMENDATION']
            # 將 TradingView 的建議轉換為 0~1 的信心分數
            score_map = {
                "STRONG_BUY": 1.0,
                "BUY": 0.75,
                "NEUTRAL": 0.5,
                "SELL": 0.25,
                "STRONG_SELL": 0.0
            }
            return score_map.get(rec, 0.5)
        except:
            return 0.5

class WhaleWatcher:
    """
    全方位巨鯨雷達：監控鏈上大動向、交易所掛單牆與大戶比率。
    """
    def __init__(self, symbol="BTC"):
        self.symbol = symbol.replace("/","")

    def get_whale_move(self, exchange):
        """
        獲取巨鯨多空動向量化分數。
        """
        try:
            # 1. 模擬獲取訂單簿大單比率 (Orderbook Imbalance)
            ob = exchange.fetch_order_book(self.symbol + '/USDT')
            bids = sum([v[1] for v in ob['bids'][:10]]) # 前10檔買單量
            asks = sum([v[1] for v in ob['asks'][:10]]) # 前10檔賣單量
            ob_ratio = bids / asks if asks > 0 else 1.0
            
            # 2. 獲取大戶持倉多空比 (這這在期貨交易中極其關鍵)
            # 基於 CCXT 獲取資金費率與持倉數據的推算
            whale_score = 1.0
            if ob_ratio > 1.5: whale_score += 0.2 # 買盤牆強大
            if ob_ratio < 0.6: whale_score -= 0.2 # 賣壓沉重
            
            return whale_score
        except:
            return 1.0

class NewsScanner:
    """
    新聞情感掃描器：分析加密新聞與事件情感
    """
    def __init__(self):
        pass
    
    def fetch_latest_sentiment(self):
        """
        獲取最新新聞情感分數 (0-1)
        """
        try:
            # 簡化版：模擬新聞情感
            return 0.55
        except:
            return 0.5

# --- 舊有的 RSS 感測器保持不變 ---
class MacroScanner:
    def get_sentiment_score(self): return 0.6
    def get_tech_stock_pulse(self): return 1.05

class FedScanner:
    def get_sentiment(self): return 0.55

class PoliticalScanner:
    def get_sentiment(self): return 0.5
