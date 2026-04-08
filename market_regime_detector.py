import numpy as np
from datetime import datetime, timedelta

class MarketRegimeDetector:
    """市場制度偵測 - 判斷市場是趨勢、震盪還是高波動"""
    
    def __init__(self, storage=None):
        self.storage = storage
        self.regimes = {
            'STRONG_UPTREND': 1,
            'UPTREND': 0.8,
            'WEAK_UPTREND': 0.6,
            'RANGING': 0.5,
            'WEAK_DOWNTREND': 0.4,
            'DOWNTREND': 0.2,
            'STRONG_DOWNTREND': 0,
            'HIGH_VOLATILITY': 0.3
        }
        self.regime_cache = {}
    
    def detect_regime(self, df, symbol='', lookback=50):
        """
        檢測市場制度 (1h 級別為準)
        Returns: (regime_name, regime_score, description)
        """
        if df is None or len(df) < lookback:
            return 'UNKNOWN', 0.5, '資料不足'
        
        recent_df = df.tail(lookback)
        closes = recent_df['close'].values
        highs = recent_df['high'].values
        lows = recent_df['low'].values
        
        # 1. 計算趨勢強度 (使用線性回歸斜率)
        x = np.arange(len(closes))
        trend_slope = np.polyfit(x, closes, 1)[0] / closes[-1]  # 標準化斜率
        
        # 2. 計算波動率 (ATR / Close)
        avg_tr = np.mean(np.diff(highs - lows))
        volatility = avg_tr / closes[-1]
        
        # 3. 計算 RSI 均值
        rsi_val = self._calc_rsi(closes, 14)
        
        # 4. 支撐阻力層級數
        support = np.min(lows[-20:])
        resistance = np.max(highs[-20:])
        range_ratio = (resistance - support) / support
        
        # 判定市場制度
        regime = 'RANGING'
        score = 0.5
        
        # 高波動判定
        if volatility > 0.03:
            regime = 'HIGH_VOLATILITY'
            score = 0.3
            desc = f"🌪️ 高波動市場 | ATR:{avg_tr:.2f} | 波動率:{volatility:.2%}"
        
        # 趨勢判定
        elif trend_slope > 0.0005 and rsi_val > 50:
            if trend_slope > 0.001:
                regime = 'STRONG_UPTREND'
                score = 1.0
                desc = "🚀 強上升趨勢"
            else:
                regime = 'UPTREND'
                score = 0.8
                desc = "📈 上升趨勢"
        elif trend_slope < -0.0005 and rsi_val < 50:
            if trend_slope < -0.001:
                regime = 'STRONG_DOWNTREND'
                score = 0.0
                desc = "📉 強下降趨勢"
            else:
                regime = 'DOWNTREND'
                score = 0.2
                desc = "📉 下降趨勢"
        
        # 弱趨勢判定
        elif 0 < trend_slope <= 0.0005:
            regime = 'WEAK_UPTREND'
            score = 0.6
            desc = "🔺 弱上升趨勢"
        elif -0.0005 <= trend_slope < 0:
            regime = 'WEAK_DOWNTREND'
            score = 0.4
            desc = "🔻 弱下降趨勢"
        else:
            regime = 'RANGING'
            score = 0.5
            desc = f"➡️ 震盪市場 | 區間:{range_ratio:.2%}"
        
        # 緩存
        self.regime_cache[symbol] = {
            'regime': regime,
            'score': score,
            'timestamp': datetime.now(),
            'volatility': volatility,
            'trend_slope': trend_slope
        }
        
        return regime, score, desc
    
    def get_trading_guidance(self, regime_name):
        """
        根據市場制度給出交易建議
        """
        guidance = {
            'STRONG_UPTREND': {
                'action': '只做多,避免做空',
                'position_size': 0.8,
                'stop_loss_atr': 1.5,
                'take_profit': 2.5
            },
            'UPTREND': {
                'action': '優先做多,謹慎做空',
                'position_size': 0.6,
                'stop_loss_atr': 1.5,
                'take_profit': 2.0
            },
            'WEAK_UPTREND': {
                'action': '雙向交易,風險均等',
                'position_size': 0.4,
                'stop_loss_atr': 1.5,
                'take_profit': 1.5
            },
            'RANGING': {
                'action': '低買高賣,冰蓋交易',
                'position_size': 0.5,
                'stop_loss_atr': 1.2,
                'take_profit': 1.0
            },
            'WEAK_DOWNTREND': {
                'action': '雙向交易,管控風險',
                'position_size': 0.4,
                'stop_loss_atr': 1.5,
                'take_profit': 1.5
            },
            'DOWNTREND': {
                'action': '優先做空,謹慎做多',
                'position_size': 0.6,
                'stop_loss_atr': 1.5,
                'take_profit': 2.0
            },
            'STRONG_DOWNTREND': {
                'action': '只做空,避免做多',
                'position_size': 0.8,
                'stop_loss_atr': 1.5,
                'take_profit': 2.5
            },
            'HIGH_VOLATILITY': {
                'action': '暫停交易或縮小頭寸',
                'position_size': 0.2,
                'stop_loss_atr': 2.0,
                'take_profit': 1.0
            }
        }
        
        return guidance.get(regime_name, guidance['RANGING'])
    
    @staticmethod
    def _calc_rsi(prices, period=14):
        """計算 RSI"""
        if len(prices) < period + 1:
            return 50
        
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 0
        rsi = 100. - 100. / (1. + rs)
        return rsi
    
    def cache_regime(self, symbol, regime_data):
        """緩存市場制度信息 (用於減少計算)"""
        self.regime_cache[symbol] = regime_data
    
    def get_cached_regime(self, symbol):
        """取得緩存的市場制度 (有效期: 5 分鐘)"""
        if symbol in self.regime_cache:
            cached = self.regime_cache[symbol]
            if datetime.now() - cached.get('timestamp', datetime.now()) < timedelta(minutes=5):
                return cached
        return None
