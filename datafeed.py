import ccxt
import pandas as pd

class DataFeed:
    def __init__(self, symbol='BTC/USDT'):
        self.exchange = ccxt.binance({
            'options': {'defaultType': 'future'} # 預設切換到期貨數據
        })
        self.symbol = symbol

    def fetch_ohlcv(self, timeframe='1m', limit=100):
        # 抓取期貨數據
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df

    def get_funding_rate(self):
        # 抓取幣安期貨資金費率 (用來監控散戶心理)
        try:
            res = self.exchange.publicGetPremiumIndex({"symbol": "BTCUSDT"})
            return float(res['lastFundingRate'])
        except:
            return 0.0001 # 預設良性費率

    def get_open_interest(self):
        # 抓取幣安期貨未平倉合約量 (監控槓桿累積)
        try:
            # 獲取最近一個週期的 OI (未平倉量)
            res = self.exchange.fapiPublicGetOpenInterest({'symbol': 'BTCUSDT'})
            latest_oi = float(res['openInterest'])
            return latest_oi
        except Exception as e:
            print(f"❌ 獲取 OI 失敗: {e}")
            return 0.0
