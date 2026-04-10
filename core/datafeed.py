import ccxt
import pandas as pd
import time
import logging

class DataFeed:
    def __init__(self, symbol='BTC/USDT'):
        # 增加連線容錯設定
        self.exchange = ccxt.binance({
            'options': {'defaultType': 'future'},
            'enableRateLimit': True,
        })
        
        # 【幣種映射修正】: 處理 Binance 不支援或名稱不同的幣種
        symbol_map = {
            'XAUT/USDT': 'PAXG/USDT', # 幣安使用 PAXG 作為黃金對接
            'SPECIAL': 'BTC/USDT'      # 特別任務隊暫時以 BTC 為掃描基準
        }
        self.symbol = symbol_map.get(symbol, symbol)
        self.clean_symbol = self.symbol.replace("/", "")
        print(f"📡 【數據鏈路】: {symbol} -> {self.symbol} 對接成功")

    def fetch_ohlcv(self, timeframe='1m', limit=100):
        """抓取 K 線數據，返回 DataFrame"""
        for i in range(3):
            try:
                ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
                return df
            except Exception as e:
                logging.warning(f"⚠️ {self.symbol} 數據抓取失敗 ({timeframe}) 第 {i+1} 次: {e}")
                time.sleep(2)
        return pd.DataFrame() # 失敗返回空

    def get_funding_rate(self):
        """獲取『當前幣種』的資金費率"""
        try:
            # 修正關鍵：使用 self.clean_symbol 而非硬編碼的 BTCUSDT
            res = self.exchange.publicGetPremiumIndex({"symbol": self.clean_symbol})
            return float(res['lastFundingRate'])
        except:
            return 0.0001

    def get_open_interest(self):
        """獲取『當前幣種』的未平倉量"""
        try:
            res = self.exchange.fapiPublicGetOpenInterest({'symbol': self.clean_symbol})
            return float(res['openInterest'])
        except:
            return 0.0
