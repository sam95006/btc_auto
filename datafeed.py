import ccxt
import pandas as pd
import time

class DataFeed:
    def __init__(self, symbol='BTC/USDT'):
        # 增加連線容錯設定
        self.exchange = ccxt.binance({
            'options': {'defaultType': 'future'},
            'enableRateLimit': True,
            # 嘗試使用不同的幣安 API 基地址來規避地區限制
            # 'urls': {'api': {'public': 'https://api1.binance.com'}} 
        })
        self.symbol = symbol

    def fetch_ohlcv(self, timeframe='1m', limit=100):
        # 增加三次重試機制，防止單次網路或地區封鎖直接卡死
        for i in range(3):
            try:
                ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
                return df
            except Exception as e:
                print(f"⚠️ 第 {i+1} 次抓取數據失敗 ({timeframe}): {e}")
                time.sleep(2)
        # 如果最終失敗，返回空數據框
        return pd.DataFrame()

    def get_funding_rate(self):
        try:
            res = self.exchange.publicGetPremiumIndex({"symbol": "BTCUSDT"})
            return float(res['lastFundingRate'])
        except:
            return 0.0001

    def get_open_interest(self):
        try:
            # 嘗試抓取期貨資料庫的未平倉量
            res = self.exchange.fapiPublicGetOpenInterest({'symbol': 'BTCUSDT'})
            return float(res['openInterest'])
        except:
            return 0.0
