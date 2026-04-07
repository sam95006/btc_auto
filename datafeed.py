import ccxt
import pandas as pd

class DataFeed:
    def __init__(self, symbol='BTC/USDT'):
        self.exchange = ccxt.binance()
        self.symbol = symbol

    def fetch_ohlcv(self, limit=100):
        # 抓取 1 分鐘 K 線 (即時 Binance 數據)
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe='1m', limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = df['close'].astype(float)
        return df
