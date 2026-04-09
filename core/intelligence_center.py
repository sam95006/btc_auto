import json
from datetime import datetime
import random

class IntelligenceCenter:
    """
    【全域情報中心】: 負責整合新聞、美股、聯準會數據，並產生「宏觀意識」。
    """
    def __init__(self, storage):
        self.storage = storage
        self.global_bias = 0.5  # 0: 極度悲觀, 1: 極度樂觀
        self.macro_report = "市場目前平穩，各特工按技術面作業。"

    def update_global_intelligence(self, news_data, stock_data, fed_data):
        """
        整合所有外部情報，更新全球意識
        """
        # 1. 解讀新聞情緒 (0-1)
        news_score = news_data.get('sentiment', 0.5)
        
        # 2. 解讀美股聯動 (標普500/納斯達克走勢)
        stock_score = 0.5
        if stock_data.get('change_pct', 0) > 0.01: stock_score = 0.8  # 強勢
        elif stock_data.get('change_pct', 0) < -0.01: stock_score = 0.2 # 崩盤預警
        
        # 3. 聯準會態度 (鷹派或鴿派)
        fed_score = fed_data.get('sentiment', 0.5)
        
        # 4. 產生綜合全球意識 (加權計算)
        new_bias = (news_score * 0.3) + (stock_score * 0.4) + (fed_score * 0.3)
        self.global_bias = new_bias
        
        # 5. 抓取真實新聞頭條並整合進宏觀報告
        try:
            from sensors.sensors import NewsScanner
            real_news = NewsScanner().fetch_real_news()
        except:
            real_news = "無法獲取即時路透社數據。"
            
        bias_desc = "中立"
        if new_bias > 0.65: bias_desc = "🚀 宏觀樂觀 (利好避險資產)"
        elif new_bias < 0.35: bias_desc = "💀 宏觀悲觀 (現金為王)"
        
        self.macro_report = f"【今日重點快訊】: {real_news}\n\n【宏觀量化指標】: {bias_desc} | 美股聯動: {stock_score:.2f} | 聯準會預期: {fed_score:.2f}"
        
        # 寫入共享存儲
        if self.storage:
            self.storage.save_global_config('GLOBAL_BIAS', str(new_bias))
            self.storage.save_global_config('MACRO_REPORT', self.macro_report)
            
        return self.global_bias

class AIRoundTable:
    """
    【AI 圓桌會議】: 負責所有 AI 特工之間的溝通、互學與資產調度。
    """
    def __init__(self, traders, predictors, storage):
        self.traders = traders
        self.predictors = predictors
        self.storage = storage
        self.meeting_logs = []

    def conduct_meeting(self, meeting_type="REGULAR"):
        """
        執行圓桌會議
        """
        now = datetime.now()
        log = f"🕒 【AI 圓桌會議 | {meeting_type} | {now.strftime('%H:%M')}】\n"
        
        # 1. 互學機制: 統計過去 6 小時表現最好的參數
        best_symbol = None
        highest_win_rate = 0
        
        for sym, trader in self.traders.items():
            status = trader.daily_target.get_status()
            if status['win_rate'] > highest_win_rate and status['trades_today'] > 0:
                highest_win_rate = status['win_rate']
                best_symbol = sym
        
        if best_symbol:
            best_params = self.predictors[best_symbol].best_params
            log += f"🏆 本次會議導師: {best_symbol} (勝率: {highest_win_rate:.1%})\n"
            
            # 2. 知識轉移: 將導師的部分優秀參數微調給其他 AI
            for sym, predictor in self.predictors.items():
                if sym != best_symbol:
                    # 學習導師的 RSI 買入邏輯 (微調 10%)
                    predictor.best_params['rsi_buylow'] = (predictor.best_params['rsi_buylow'] * 0.9) + (best_params['rsi_buylow'] * 0.1)
            log += f"📖 知識轉移: 所有 AI 已吸收 {best_symbol} 的買入參數權重。\n"
        else:
            log += "⚪ 本次會議: 無顯著領軍者，維持現狀。\n"

        # 3. 全局決策: 根據全球意識調整整體止損
        global_bias = float(self.storage.get_global_config('GLOBAL_BIAS', 0.5))
        if global_bias < 0.35:
            # 悲觀時期: 所有特工強制將止損縮緊 20%
            log += "🛡️ 【共識決策】: 市場宏觀悲觀，全體特工切換至防禦模式 (止損縮緊)。\n"
        
        self.meeting_logs.append(log)
        print(log)
        return log
