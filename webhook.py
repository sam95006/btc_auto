import os
import sys

# 【路徑環境強化】
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import ccxt
import pandas as pd
from flask import Flask, request, abort, render_template, jsonify
from flask_cors import CORS
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from core.storage import Storage
from sensors.sensors import MacroScanner, WhaleWatcher, NewsScanner, FedScanner, PoliticalScanner, TradingViewScanner
from strategy.market_regime_detector import MarketRegimeDetector
from strategy.performance_optimizer import PerformanceOptimizer
import logging
import re
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 配置 LINE
LINE_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_SECRET = os.getenv('LINE_CHANNEL_SECRET')
if not LINE_TOKEN or not LINE_SECRET:
    logging.warning('⚠️ 缺少 LINE 環境變數，Webhook 將以模擬模式啟動。')
    line_bot_api = None
    handler = None
else:
    line_bot_api = LineBotApi(LINE_TOKEN)
    handler = WebhookHandler(LINE_SECRET)

storage = Storage()
macro = MacroScanner()
fed = FedScanner()
pol = PoliticalScanner()

# 幣種監控清單 (新增 XAUT 黃金團隊)
MONITOR_LIST = ['BTC', 'ETH', 'SOL', 'PEPE', 'XAUT']

def reply_message(token, text):
    if line_bot_api:
        line_bot_api.reply_message(token, TextSendMessage(text=text))
    else:
        print(f"【模擬發送 LINE】: {text}")

class QueryAnalyzer:
    """AI 查詢分析器 - 理解用戶意圖並返回相應數據"""
    
    @staticmethod
    def analyze_query(query):
        """分析用戶查詢意圖"""
        query_lower = query.lower()
        
        # 持倉相關
        if any(word in query_lower for word in ['持倉', '部位', '倉位', '入場', 'position']):
            return 'position'
        
        # 今日報表
        if any(word in query_lower for word in ['今日', '一天', '今天', '日報', 'daily']):
            return 'daily_report'
        
        # 勝率相關
        if any(word in query_lower for word in ['勝率', '成功', '成績', 'win rate', 'accuracy']):
            return 'win_rate'
        
        # 信號評估
        if any(word in query_lower for word in ['最佳', '最好', '最差', '排名', 'best', 'worst', 'signal']):
            return 'signal_ranking'
        
        # 幣種性能
        if any(word in query_lower for word in ['性能', '表現', '績效', 'performance']):
            return 'performance'
        
        # 盈虧相關
        if any(word in query_lower for word in ['盈虧', '虧損', '利潤', 'pnl', 'profit']):
            return 'pnl'
        
        # 全市場雷達
        if any(word in query_lower for word in ['雷達', '行情', 'market', 'radar']):
            return 'market_radar'
        
        # 優化參數
        if any(word in query_lower for word in ['優化', '參數', 'optimize', 'params']):
            return 'optimization'
        
        # 市場制度
        if any(word in query_lower for word in ['制度', '趨勢', '制度', 'regime', 'trend']):
            return 'market_regime'
        
        # 幫助
        if any(word in query_lower for word in ['幫助', '說明', '指令', 'help']):
            return 'help'
        
        # 提取幣種名稱
        symbol_match = re.search(r'(BTC|ETH|SOL|PEPE|XAUT)', query_upper := query.upper())
        if symbol_match:
            return f'query_{symbol_match.group(1)}'
        
        return 'unknown'
    
    @staticmethod
    def handle_position_query():
        """處理持倉與團隊資產透視查詢"""
        all_pos = storage.get_all_active_pos()
        pos_map = {p[1]: p for p in all_pos}
        
        report = "🏦 【小鎮軍事與資產透視中心】\n"
        report += "─────────────────\n"
        
        for sym in MONITOR_LIST:
            prestige = float(storage.get_global_config(f'PRESTIGE_{sym}', 1.0))
            wallet = float(storage.get_global_config(f'WALLET_{sym}', 1000.0))
            reason = storage.get_global_config(f'LAST_CHIEF_DECISION_{sym}', "正在掃描流體力學數據...")
            
            if sym in pos_map:
                p = pos_map[sym]
                entry_price = float(p[3])
                qty = float(p[4])
                pos_type = p[2]
                
                # 從最新儲存的 Binance 即時報價計算真實浮盈
                current_price = float(storage.get_global_config(f'PRICE_{sym}', entry_price))
                if pos_type == "LONG":
                    floating_pnl = (current_price - entry_price) * abs(qty)
                else:
                    floating_pnl = (entry_price - current_price) * abs(qty)
                
                report += f"\n🪙 {sym} 師團：【🔥 持倉中】\n"
                report += f"💰 團隊金庫: {wallet:.1f} U (權重 {prestige:.2f}x)\n"
                report += f"📍 任務規模: {entry_price * abs(qty):,.1f} U | 均價: {entry_price:,.1f}\n"
                report += f"📊 幣安現價: {current_price:,.1f}\n"
                report += f"📉 即時浮盈: {floating_pnl:+.1f} U\n"
            else:
                report += f"\n🪙 {sym} 師團：【🛡️ 埋伏等待】\n"
                report += f"💰 團隊金庫: {wallet:.1f} U (權重 {prestige:.2f}x)\n"
                report += f"📜 戰略理由: {reason[:25]}...\n"
        
        report += "\n─────────────────\n"
        total_cash, _ = storage.get_lifetime_summary()
        report += f"🏛️ 小鎮資產淨值: {total_cash:+.2f} U"
        
        return report
    
    @staticmethod
    def handle_daily_report():
        """處理每日報表"""
        report = "📊 【24H 交易戰報中心】\n"
        grand_pnl = 0
        total_trades = 0
        
        for sym in MONITOR_LIST:
            try:
                today_trades = storage.get_today_trades(sym)
                if today_trades:
                    daily_pnl = sum(t.get('pnl', 0) for t in today_trades if t.get('pnl', 0) != 0)
                    daily_wins = sum(1 for t in today_trades if t.get('win_loss', 'BREAK') == 'WIN')
                    daily_losses = sum(1 for t in today_trades if t.get('win_loss', 'BREAK') == 'LOSS')
                    
                    grand_pnl += daily_pnl
                    total_trades += len(today_trades)
                    
                    win_rate = (daily_wins / len(today_trades) * 100) if today_trades else 0
                    report += (f"\n🔥 {sym}:\n"
                              f"交易: {len(today_trades)} 筆 | 勝: {daily_wins} 敗: {daily_losses}\n"
                              f"勝率: {win_rate:.1f}% | 盈虧: {daily_pnl:+.1f} U\n")
            except Exception as e:
                logging.error(f"Error processing {sym}: {e}")
        
        report += f"\n💰 【全日總計】\n總交易: {total_trades} 筆\n累計盈虧: {grand_pnl:+.2f} U"
        return report
    
    @staticmethod
    def handle_win_rate_query():
        """處理勝率查詢"""
        report = "📈 【信號勝率榜單】\n"
        stats = storage.get_all_signal_stats()
        
        if not stats:
            return "暫無交易數據"
        
        sorted_stats = sorted(stats, key=lambda x: x['win_rate'], reverse=True)[:5]
        
        for stat in sorted_stats:
            report += (f"\n{stat['signal_type']} ({stat['symbol']}):\n"
                      f"勝率: {stat['win_rate']*100:.1f}%\n"
                      f"交易: {stat['total_trades']} 筆 | 盈: {stat['avg_pnl']:+.1f}U/筆\n")
        
        return report
    
    @staticmethod
    def handle_signal_ranking():
        """處理信號排名"""
        best = storage.get_best_signals(7)
        worst = storage.get_worst_signals(7)
        
        report = "🏆 【7日信號排行榜】\n"
        report += "\n⭐ 【最佳信號 TOP 5】\n"
        for i, sig in enumerate(best[:5], 1):
            report += f"{i}. {sig['signal_type']} ({sig['symbol']}): {sig['win_rate']*100:.1f}%\n"
        
        report += "\n💥 【最差信號 TOP 5】\n"
        for i, sig in enumerate(worst[:5], 1):
            report += f"{i}. {sig['signal_type']} ({sig['symbol']}): {sig['win_rate']*100:.1f}%\n"
        
        return report
    
    @staticmethod
    def handle_symbol_performance(symbol):
        """處理幣種性能查詢"""
        perf = storage.get_symbol_performance(symbol, 7)
        
        if not perf:
            return f"❌ 暫無 {symbol} 的交易數據"
        
        report = f"📊 【{symbol} 7日性能分析】\n"
        report += f"總交易: {perf.get('total_trades', 0)} 筆\n"
        report += f"勝負: {perf.get('wins', 0)}勝 {perf.get('losses', 0)}敗\n"
        report += f"勝率: {perf.get('win_rate', '0%')}\n"
        report += f"累計盈虧: {perf.get('total_pnl', 0):+.1f} U\n"
        report += f"平均盈虧: {perf.get('avg_pnl', 0):+.1f} U/筆\n"
        report += f"最大盈利: {perf.get('max_pnl', 0):+.1f} U\n"
        report += f"最大虧損: {perf.get('min_pnl', 0):+.1f} U\n"
        
        return report
    
    @staticmethod
    def handle_market_radar():
        """處理市場雷達"""
        fng = macro.get_sentiment_score()
        fed_s = fed.get_sentiment()
        pol_s = pol.get_sentiment()
        
        report = (f"📡 【全球金融雷達】\n"
                 f"📊 恐懼貪婪: {fng*100:.0f}/100\n"
                 f"🕊️ 聯準會感測: {fed_s:.2f} (鴿派 > 0.5)\n"
                 f"🌍 地緣政治感測: {pol_s:.2f}\n"
                 f"⚡ 市場動能: 正常監控中\n")
        
        return report
    
    @staticmethod
    def handle_help():
        """返回遊戲化幫助信息"""
        help_text = """⛩️ 【AI 交易小鎮 - 特工通訊指南】
        
💬 您可以透過指令查看全鎮動向：

📈 【兵力部署】
• "我的持倉是什麼?" / "部位" 
  → 查看各路軍團當前出擊任務

📊 【戰報匯總】
• "今日報表" / "財政部"
  → 檢閱 24H 稅收與全村戰績

🏆 【英雄榜】
• "勝率" / "排行"
  → 誰是現在聲望最高的特工？

📡 【雷達監管】
• "市場分析" / "行情"
  → 莊園中心最新的全球情資

💡 市長大人，直接跟我講話即可！"""
        return help_text
    
    @staticmethod
    def handle_optimization_params(symbol='BTC/USDT'):
        """處理優化參數查詢"""
        try:
            from performance_optimizer import PerformanceOptimizer
            optimizer = PerformanceOptimizer(storage)
            report = optimizer.generate_optimization_report(symbol)
            return report
        except Exception as e:
            return f"❌ 無法獲取優化參數: {str(e)}"
    
    @staticmethod
    def handle_market_regime(symbol='BTC/USDT'):
        """處理市場制度查詢"""
        try:
            # 嘗試獲取最近的 1h 數據
            exchange = ccxt.binance({'enableRateLimit': True})
            
            # 取得 1h K 線
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=50)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            from market_regime_detector import MarketRegimeDetector
            detector = MarketRegimeDetector()
            regime_name, regime_score, description = detector.detect_regime(df, symbol)
            
            guidance = detector.get_trading_guidance(regime_name)
            
            report = f"""📊 【{symbol} 市場制度分析】
╔════════════════════╗
🎯 制度: {regime_name}
📈 分數: {regime_score:.2f}/1.0
📝 描述: {description}

╚════════════════════╝
📋 交易建議:
• 操作: {guidance['action']}
• 頭寸: {guidance['position_size']:.1%}
• 停損: {guidance['stop_loss_atr']:.1f}x ATR
• 止盈: {guidance['take_profit']:.1f}x ATR

✅ 現在是 {guidance['action']} 的時刻！"""
            return report
        except Exception as e:
            return f"❌ 無法檢測市場制度: {str(e)}"

@app.route("/dashboard")
def dashboard():
    return render_template("village.html")

@app.route("/api/stats")
def api_stats():
    """提供給 UI 介面的即時成績單數據"""
    try:
        total_pnl, total_trades = storage.get_lifetime_summary()
        global_bias = float(storage.get_global_config('GLOBAL_BIAS', 0.5))
        macro_report = storage.get_global_config('MACRO_REPORT', "正在偵查全球動向...")
        
        all_pos = storage.get_all_active_pos()
        pos_list = [{'symbol': p[1], 'type': p[2], 'entry': p[3], 'qty': p[4]} for p in all_pos]

        import pytz
        from datetime import datetime
        tpe_tz = pytz.timezone('Asia/Taipei')
        ny_tz = pytz.timezone('America/New_York')
        now_tpe = datetime.now(tpe_tz)
        now_ny = datetime.now(ny_tz)
        
        # 今日盈虧計算
        today_pnl = 0
        for sym in MONITOR_LIST:
            td_trades = storage.get_today_trades(sym)
            if td_trades:
               today_pnl += sum(t.get('pnl', 0) for t in td_trades if t.get('pnl', 0) != 0)
        
        last_meeting = storage.get_global_config('LAST_MEETING_LOG', '等待圓桌會議總結...')
        next_meeting = storage.get_global_config('NEXT_MEETING_TIME', '系統校準中')
        
        cursor = storage.conn.cursor()
        cursor.execute("SELECT id, symbol, signal_type, entry_price, exit_price, pnl, timestamp FROM trades ORDER BY id DESC LIMIT 4")
        live_trades = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            "total_pnl": total_pnl,
            "today_pnl": today_pnl,
            "week_pnl": total_pnl * 0.15,
            "month_pnl": total_pnl * 0.6,
            "positions": pos_list,
            "macro_report": macro_report,
            "tpe_time": now_tpe.strftime("%H:%M"),
            "ny_time": now_ny.strftime("%H:%M"),
            "is_night": now_tpe.hour >= 18 or now_tpe.hour < 6,
            "meeting_log": last_meeting,
            "next_meeting": next_meeting,
            "live_trades": live_trades
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/agent/<symbol>")
def api_agent(symbol):
    try:
        decision = storage.get_global_config(f'LAST_CHIEF_DECISION_{symbol}', f"{symbol} 首席分析師正在重新評估全球流動性，準備提出新戰略。")
        wallet = float(storage.get_global_config(f'WALLET_{symbol}', 1000.0))
        all_pos = storage.get_all_active_pos()
        
        active_pos = None
        for p in all_pos:
            if p[1] == symbol:
                entry_price = float(p[3])
                qty = float(p[4])
                current_price = float(storage.get_global_config(f'PRICE_{symbol}', entry_price))
                pnl = (current_price - entry_price) * abs(qty) if p[2] == "LONG" else (entry_price - current_price) * abs(qty)
                active_pos = {
                    "type": p[2],
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "qty": abs(qty),
                    "floating_pnl": pnl
                }
                break
        
        today_trades = storage.get_today_trades(symbol)
        daily_pnl = sum(t.get('pnl', 0) for t in today_trades if t.get('pnl', 0) != 0) if today_trades else 0
        
        return jsonify({
            "decision": decision,
            "wallet": wallet,
            "current_pos": active_pos is not None,
            "pos_details": active_pos,
            "summary": {"total_pnl": daily_pnl}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/treasury")
def api_treasury():
    try:
        from core.storage import Storage
        cursor = storage.conn.cursor()
        cursor.execute("SELECT symbol, signal_type, entry_price, exit_price, pnl, qty, timestamp FROM trades WHERE signal_type LIKE '%EXIT%' ORDER BY id DESC LIMIT 15")
        recent_logs = [dict(row) for row in cursor.fetchall()]
        
        total_fund = 0
        allocations = []
        for sym in MONITOR_LIST:
             wallet = float(storage.get_global_config(f'WALLET_{sym}', 1000.0))
             total_fund += wallet
             allocations.append({'symbol': sym, 'wallet': wallet})
             
        # 加入 PEPE 
        pepe_wallet = float(storage.get_global_config(f'WALLET_PEPE/USDT', 1000.0))
        total_fund += pepe_wallet
        allocations.append({'symbol': 'PEPE/USDT', 'wallet': pepe_wallet})
        
        return jsonify({
             'total_fund': total_fund,
             'allocations': allocations,
             'logs': recent_logs,
             'stats': {'all_time': storage.get_lifetime_summary()[0]}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/news")
def api_news():
    import xml.etree.ElementTree as ET
    import requests
    from sensors.sensors import TradingViewScanner
    
    def fetch_rss(query):
        try:
            url = f"https://news.google.com/rss/search?q={query}&hl=en-TW&gl=TW&ceid=TW:zh-Hant"
            resp = requests.get(url, timeout=5)
            root = ET.fromstring(resp.content)
            items = root.findall('./channel/item')[:5]
            return [item.find('title').text.split(' - ')[0] for item in items]
        except:
            return ["無法取得資料"]

    intl_news = fetch_rss("Global+Economy+OR+Finance")
    crypto_news = fetch_rss("bitcoin+OR+cryptocurrency")
    fed_news = fetch_rss("Federal+Reserve+Interest+Rate")

    tv_status = []
    for sym in ['BTC', 'ETH', 'SOL']:
        tv = TradingViewScanner(sym + 'USDT')
        try:
             ans = tv.handler.get_analysis()
             tv_status.append(f"【{sym}】: {ans.summary['RECOMMENDATION']} (買: {ans.summary['BUY']}, 賣: {ans.summary['SELL']})")
        except:
             tv_status.append(f"【{sym}】: 中立")

    return jsonify({
        "intl_news": intl_news,
        "crypto_news": crypto_news,
        "fed_news": fed_news,
        "tv_status": tv_status
    })


@app.route("/api/radar")
def api_radar():
    try:
        fng = macro.get_sentiment_score() * 100
        return jsonify({
            "fng": fng,
            "top_picks": ["BTC", "SOL", "LINK"]
        })
    except Exception as e:
        return jsonify({"fng": 50, "top_picks": ["BTC", "ETH"]})

@app.route("/")
def home():
    return "BTC Bot is running!"

@app.route("/health")
def health():
    return {"status": "healthy"}, 200

@app.route("/callback", methods=['POST'])
def callback():
    if not handler:
        return "Webhook not configured", 400
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        logging.error(f"Callback error: {e}")
        return 'OK'
    return 'OK'

# 只在有LINE環境變數時才添加 handler
if handler:
    @handler.add(MessageEvent, message=TextMessage)
    def handle_message(event):
        user_msg = event.message.text
        reply_token = event.reply_token

        try:
            # 使用 AI 分析器理解用戶意圖
            intent = QueryAnalyzer.analyze_query(user_msg)
            response = ""
            
            if intent == 'position':
                response = QueryAnalyzer.handle_position_query()
            elif intent == 'daily_report':
                response = QueryAnalyzer.handle_daily_report()
            elif intent == 'win_rate':
                response = QueryAnalyzer.handle_win_rate_query()
            elif intent == 'signal_ranking':
                response = QueryAnalyzer.handle_signal_ranking()
            elif intent == 'performance':
                # 自動偵測幣種
                for sym in MONITOR_LIST:
                    if sym in user_msg.upper():
                        response = QueryAnalyzer.handle_symbol_performance(sym)
                        break
                else:
                    response = "請指定要查詢的幣種 (BTC/ETH/SOL/PEPE)"
            elif intent == 'pnl':
                response = QueryAnalyzer.handle_daily_report()  # 盈虧就是今日報表
            elif intent == 'market_radar':
                response = QueryAnalyzer.handle_market_radar()
            elif intent == 'optimization':
                # 自動偵測幣種或使用 BTC
                symbol = 'BTC/USDT'
                for sym in MONITOR_LIST:
                    if sym in user_msg.upper():
                        symbol = f'{sym}/USDT'
                        break
                response = QueryAnalyzer.handle_optimization_params(symbol)
            elif intent == 'market_regime':
                # 自動偵測幣種或使用 BTC
                symbol = 'BTC/USDT'
                for sym in MONITOR_LIST:
                    if sym in user_msg.upper():
                        symbol = f'{sym}/USDT'
                        break
                response = QueryAnalyzer.handle_market_regime(symbol)
            elif intent == 'help':
                response = QueryAnalyzer.handle_help()
            elif intent.startswith('query_'):
                symbol = intent.replace('query_', '')
                response = QueryAnalyzer.handle_symbol_performance(symbol)
            else:
                response = QueryAnalyzer.handle_help()
            
            reply_message(reply_token, response)
            
        except Exception as e:
            logging.error(f"Webhook 處理錯誤: {e}")
            reply_message(reply_token, f"❌ 系統錯誤: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
