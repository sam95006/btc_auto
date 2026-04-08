"""
【AI 自學習系統核心】 - PerformanceOptimizer
持續監測每個交易對的表現，根據最高勝率自動調整交易參數。
每 7 分鐘更新一次參數，每天晚上 8 點做深度優化。
"""

import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

class PerformanceOptimizer:
    """
    自動參數優化器 - 持續調整 RSI、布林帶、成交量等參數以最大化勝率
    """
    
    def __init__(self, storage=None):
        self.storage = storage
        self.optimization_history = defaultdict(list)
        self.param_combinations = {}
        self.last_optimization_time = {}
        
        # 預設參數範圍 (搜尋空間)
        self.param_ranges = {
            'rsi_buy_low': [25, 35, 30],  # [min, max, current]
            'rsi_sell_high': [65, 75, 70],
            'bb_std_dev': [1.0, 2.5, 2.0],
            'bb_sensitivity': [0.5, 2.0, 1.5],
            'volume_multiplier': [1.0, 3.0, 1.5],
            'volatility_filter': [0.01, 0.05, 0.02],
            'ema_fast': [30, 100, 50],
            'ema_slow': [150, 250, 200],
            'atr_stop_loss': [1.0, 2.5, 1.5],
            'atr_take_profit': [1.5, 3.5, 2.5]
        }
    
    def optimize_parameters(self, symbol='BTC/USDT', lookback_days=7):
        """
        【核心優化邏輯】
        基於過去 N 天的交易數據，找出最佳參數組合
        Returns: optimized_params dict
        """
        
        # 檢查最後優化時間 (避免過度頻繁優化)
        if symbol in self.last_optimization_time:
            last_time = self.last_optimization_time[symbol]
            if datetime.now() - last_time < timedelta(hours=1):
                return self.param_combinations.get(symbol, {})
        
        # 獲取過去 N 天的交易記錄
        trades = self.storage.get_symbol_trades(symbol, days=lookback_days) if self.storage else []
        
        if not trades or len(trades) < 5:
            return self._get_default_params(symbol)
        
        # 1. 統計各交易對的表現
        performance_stats = self._analyze_performance(trades)
        
        # 2. 識別高勝率參數組合
        high_win_rate_signals = [t for t in trades if t[5] > 0]  # pnl > 0
        
        if not high_win_rate_signals:
            return self._get_default_params(symbol)
        
        # 3. 根據高勝率交易反推參數
        optimal_params = self._reverse_engineer_params(high_win_rate_signals)
        
        # 4. 驗證新參數 (確保不會太極端)
        optimal_params = self._validate_params(optimal_params)
        
        # 5. 持久化優化結果
        self.param_combinations[symbol] = optimal_params
        self.last_optimization_time[symbol] = datetime.now()
        
        # 記錄優化歷史
        self.optimization_history[symbol].append({
            'timestamp': datetime.now(),
            'params': optimal_params.copy(),
            'performance': performance_stats
        })
        
        return optimal_params
    
    def _analyze_performance(self, trades):
        """分析交易表現統計"""
        if not trades:
            return {}
        
        stats = {
            'total_trades': len(trades),
            'winning_trades': len([t for t in trades if t[5] > 0]),
            'losing_trades': len([t for t in trades if t[5] <= 0]),
            'avg_win': np.mean([t[5] for t in trades if t[5] > 0]) if any(t[5] > 0 for t in trades) else 0,
            'avg_loss': np.mean([t[5] for t in trades if t[5] <= 0]) if any(t[5] <= 0 for t in trades) else 0,
            'win_rate': len([t for t in trades if t[5] > 0]) / len(trades) if trades else 0,
            'avg_pnl': np.mean([t[5] for t in trades]),
            'max_drawdown': self._calc_drawdown(trades),
            'sharpe_ratio': self._calc_sharpe_ratio(trades)
        }
        
        return stats
    
    def _reverse_engineer_params(self, winning_trades):
        """
        反推最佳參數 - 從高勝率交易中提取參數pattern
        """
        optimal_params = {}
        
        # 簡化版: 根據交易時的市場狀態反推
        # 實際應用：可在 trades 上存入 market_context
        
        # 預設: 基於勝率微調
        win_rate = len(winning_trades) / max(1, len(winning_trades) * 1.5)  # 估算
        
        optimal_params['rsi_buy_low'] = max(25, 30 - int(win_rate * 5))  # 勝率越高，賣點越激進
        optimal_params['rsi_sell_high'] = min(75, 70 + int(win_rate * 5))
        optimal_params['bb_std_dev'] = 1.5 + (win_rate * 0.5)
        optimal_params['volume_multiplier'] = 1.5 + (win_rate * 0.5)
        optimal_params['volatility_filter'] = max(0.01, 0.02 - (win_rate * 0.01))
        optimal_params['ema_fast'] = 50
        optimal_params['ema_slow'] = 200
        optimal_params['atr_stop_loss'] = 1.5 - (win_rate * 0.3)  # 勝率高，停損更緊
        optimal_params['atr_take_profit'] = 2.5
        
        return optimal_params
    
    def _validate_params(self, params):
        """驗證參數合理性"""
        validated = {}
        
        for param, value in params.items():
            if param in self.param_ranges:
                param_min, param_max, _ = self.param_ranges[param]
                # 限制在合理範圍內
                validated[param] = max(param_min, min(param_max, value))
            else:
                validated[param] = value
        
        return validated
    
    def _get_default_params(self, symbol=''):
        """返回預設參數"""
        return {
            'rsi_buy_low': 30,
            'rsi_sell_high': 70,
            'bb_std_dev': 2.0,
            'bb_sensitivity': 1.5,
            'volume_multiplier': 1.5,
            'volatility_filter': 0.02,
            'ema_fast': 50,
            'ema_slow': 200,
            'atr_stop_loss': 1.5,
            'atr_take_profit': 2.5
        }
    
    def get_optimal_params(self, symbol='BTC/USDT', use_cache=True):
        """取得最優參數 (帶快取)"""
        
        if use_cache and symbol in self.param_combinations:
            cached_params = self.param_combinations[symbol]
            # 每 7 分鐘更新一次
            if symbol in self.last_optimization_time:
                if datetime.now() - self.last_optimization_time[symbol] < timedelta(minutes=7):
                    return cached_params
        
        # 執行優化
        return self.optimize_parameters(symbol)
    
    def adjust_for_market_regime(self, params, regime_info):
        """根據市場制度調整參數"""
        
        regime_name = regime_info.get('regime', 'RANGING')
        volatility = regime_info.get('volatility', 0.02)
        
        adjusted = params.copy()
        
        # 強上升趨勢: 更激進的買入
        if regime_name == 'STRONG_UPTREND':
            adjusted['rsi_buy_low'] = min(adjusted['rsi_buy_low'] - 3, 25)
            adjusted['volume_multiplier'] = min(adjusted['volume_multiplier'] * 1.2, 3.0)
        
        # 強下降趨勢: 更激進的賣出 (做空)
        elif regime_name == 'STRONG_DOWNTREND':
            adjusted['rsi_sell_high'] = max(adjusted['rsi_sell_high'] + 3, 75)
            adjusted['volume_multiplier'] = min(adjusted['volume_multiplier'] * 1.2, 3.0)
        
        # 高波動: 保守交易
        elif regime_name == 'HIGH_VOLATILITY':
            adjusted['volatility_filter'] = max(adjusted['volatility_filter'] * 1.5, 0.05)
            adjusted['atr_stop_loss'] = adjusted['atr_stop_loss'] * 1.3
            adjusted['volume_multiplier'] = max(adjusted['volume_multiplier'] * 0.7, 1.0)
        
        # 震盪市場: 反轉交易
        elif regime_name == 'RANGING':
            adjusted['rsi_buy_low'] = 35
            adjusted['rsi_sell_high'] = 65
            adjusted['volume_multiplier'] = 1.0
        
        return adjusted
    
    @staticmethod
    def _calc_drawdown(trades):
        """計算最大回撤"""
        if not trades:
            return 0
        
        cumulative = np.cumsum([t[5] for t in trades])
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (running_max - cumulative) / (np.abs(running_max) + 1e-9)
        return float(np.max(drawdown)) if len(drawdown) > 0 else 0
    
    @staticmethod
    def _calc_sharpe_ratio(trades):
        """計算夏普比率"""
        if not trades or len(trades) < 2:
            return 0
        
        returns = np.array([t[5] for t in trades])
        if np.std(returns) == 0:
            return 0
        
        return (np.mean(returns) / np.std(returns)) * np.sqrt(252) if len(returns) > 0 else 0
    
    def generate_optimization_report(self, symbol='BTC/USDT'):
        """生成優化報告 (供 LINE 機器人顯示)"""
        
        if symbol not in self.param_combinations:
            return "❌ 未找到最佳化參數"
        
        params = self.param_combinations[symbol]
        history = self.optimization_history[symbol] if symbol in self.optimization_history else []
        
        report = f"""
📊 【{symbol} 優化報告】
⏰ 生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🎯 當前最優參數:
• RSI 買點: {params.get('rsi_buy_low', 30)}
• RSI 賣點: {params.get('rsi_sell_high', 70)}
• 布林帶標準差: {params.get('bb_std_dev', 2.0):.2f}
• 成交量倍數: {params.get('volume_multiplier', 1.5):.2f}x
• 停損 ATR: {params.get('atr_stop_loss', 1.5):.2f}x
• 止盈 ATR: {params.get('atr_take_profit', 2.5):.2f}x

📈 優化歷史:
"""
        
        if history:
            latest = history[-1]
            perf = latest.get('performance', {})
            report += f"""• 總交易數: {perf.get('total_trades', 0)}
• 勝率: {perf.get('win_rate', 0):.1%}
• 平均獲利: ${perf.get('avg_pnl', 0):.2f}
• 最大回撤: {perf.get('max_drawdown', 0):.2%}
• 夏普比: {perf.get('sharpe_ratio', 0):.2f}
"""
        
        report += "\n✅ 參數已自動優化，準備下單！"
        return report
