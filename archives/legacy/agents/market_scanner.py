"""
動態市場掃描系統 - 自動尋找符合交易條件的新幣種
"""
import ccxt
import time
from datetime import datetime
from indicators import calculate_all

class DynamicMarketScanner:
    """掃描全市場尋找符合條件的交易機會"""
    
    def __init__(self, storage=None):
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.storage = storage
        self.scanned_symbols = set()
        self.qualified_symbols = []
    
    def get_top_symbols(self, limit=20):
        """獲取市值前N的幣種"""
        try:
            # 獲取所有交易對
            symbols = self.exchange.symbols
            usdt_pairs = [s for s in symbols if 'USDT' in s and '/' in s]
            
            # 返回前 limit 個 USDT 交易對
            return usdt_pairs[:limit]
        except Exception as e:
            print(f"❌ 獲取交易對列表失敗: {e}")
            return []
    
    def analyze_symbol(self, symbol, storage=None):
        """分析單個幣種是否符合交易條件"""
        try:
            # 獲取 1m 數據
            df = calculate_all(self._fetch_ohlcv(symbol, '1m', 100))
            
            if df.empty:
                return False, "數據不足"
            
            latest = df.iloc[-1]
            
            # 評估條件
            scores = {}
            
            # 1. RSI 條件 (超買超賣信號)
            rsi = latest.get('RSI', 50)
            scores['rsi'] = 1.0 if (rsi < 30 or rsi > 70) else 0.5
            
            # 2. 布林帶條件
            bb_upper = latest.get('BB_Upper', 0)
            bb_lower = latest.get('BB_Lower', 0)
            close = latest.get('close', 0)
            if close > 0 and bb_upper > 0 and bb_lower > 0:
                scores['bb'] = 1.0 if (close < bb_lower * 1.005 or close > bb_upper * 0.995) else 0.5
            else:
                scores['bb'] = 0.3
            
            # 3. 波動率條件
            volatility = df['close'].pct_change().std()
            scores['volatility'] = 1.0 if volatility > 0.01 else 0.5
            
            # 4. 成交量條件
            volume = latest.get('volume', 0)
            vol_ma = df['volume'].mean()
            scores['volume'] = 1.0 if volume > vol_ma * 1.5 else 0.5
            
            # 5. EMA 200 趨勢
            ema200 = latest.get('EMA200', close)
            if close > 0 and ema200 > 0:
                is_uptrend = close > ema200
                scores['trend'] = 1.0 if is_uptrend else 0.5
            else:
                scores['trend'] = 0.3
            
            # 計算總分
            total_score = sum(scores.values()) / len(scores)
            
            # 符合條件：總分 > 0.65 且 RSI 有效
            qualified = total_score > 0.65 and scores['rsi'] > 0.5
            
            return qualified, scores
            
        except Exception as e:
            return False, f"分析失敗: {e}"
    
    def _fetch_ohlcv(self, symbol, timeframe, limit):
        """安全地抓取 OHLCV 數據"""
        try:
            for attempt in range(3):
                try:
                    return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                except Exception:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        raise
        except:
            return []
    
    def scan_market(self, limit=20):
        """掃描市場並找出符合條件的幣種"""
        print(f"🔍 正在掃描前 {limit} 大幣種...")
        
        qualified = []
        symbols = self.get_top_symbols(limit)
        
        # 過濾掉已監控的幣種
        symbols_to_check = [s for s in symbols if s not in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PEPE/USDT']]
        
        for symbol in symbols_to_check[:limit]:
            try:
                is_qualified, scores = self.analyze_symbol(symbol)
                
                if is_qualified:
                    qualified.append({
                        'symbol': symbol,
                        'scores': scores,
                        'timestamp': datetime.now()
                    })
                    print(f"✅ {symbol} 符合條件！")
                    
            except Exception as e:
                print(f"⚠️ {symbol} 分析失敗: {e}")
            
            # 避免 API 限速
            time.sleep(0.5)
        
        self.qualified_symbols = qualified
        print(f"🎯 找到 {len(qualified)} 個符合條件的幣種")
        
        return qualified
    
    def get_top_opportunities(self, limit=5):
        """獲取評分最高的機會"""
        if not self.qualified_symbols:
            return []
        
        # 按評分排序
        sorted_symbols = sorted(
            self.qualified_symbols,
            key=lambda x: sum(x['scores'].values()) / len(x['scores']),
            reverse=True
        )
        
        return sorted_symbols[:limit]
