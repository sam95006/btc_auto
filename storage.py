import sqlite3
from datetime import datetime, timedelta
import os
import json

class Storage:
    def __init__(self, db_name="trading.db"):
        # 直接使用根目錄，確保在 Zeabur/Heroku 等環境中具備寫入權限
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 返回字典格式
        self.init_db()

    def init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            daily_pnl REAL,
            cumulative_pnl REAL
        )''')
        
        # 完整的交易記錄
        cursor.execute('''CREATE TABLE IF NOT EXISTS trades
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          timestamp TEXT, 
                          symbol TEXT,
                          signal_type TEXT,
                          entry_price REAL, 
                          exit_price REAL, 
                          qty REAL, 
                          pnl REAL, 
                          total_pnl REAL,
                          direction TEXT,
                          win_loss TEXT,
                          market_context TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS active_pos
                         (id INTEGER PRIMARY KEY, symbol TEXT, type TEXT, entry_price REAL, qty REAL, trailing_high REAL)''')
        
        # 交易教訓記錄 (自我進化大腦用)
        cursor.execute('''CREATE TABLE IF NOT EXISTS lessons (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            pnl REAL,
                            reason TEXT,
                            market_context TEXT,
                            signal_type TEXT,
                            is_learned INTEGER DEFAULT 0)''')
        
        # 信號勝率統計表
        cursor.execute('''CREATE TABLE IF NOT EXISTS signal_stats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT,
                            signal_type TEXT,
                            total_trades INTEGER DEFAULT 0,
                            winning_trades INTEGER DEFAULT 0,
                            losing_trades INTEGER DEFAULT 0,
                            win_rate REAL DEFAULT 0.0,
                            avg_pnl REAL DEFAULT 0.0,
                            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(symbol, signal_type))''')
        
        self.conn.commit()

    def log_lesson(self, symbol, pnl, reason, context):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO lessons (symbol, pnl, reason, market_context) VALUES (?, ?, ?, ?)",
                       (symbol, pnl, reason, context))
        self.conn.commit()

    def get_recent_lessons(self, symbol, limit=10):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM lessons WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?", (symbol, limit))
        return cursor.fetchall()

    def update_active_pos(self, symbol, pos_type, price, qty, trailing_high=0):
        cursor = self.conn.cursor()
        if qty == 0:
            cursor.execute("DELETE FROM active_pos WHERE symbol = ?", (symbol,))
        else:
            cursor.execute("REPLACE INTO active_pos (id, symbol, type, entry_price, qty, trailing_high) VALUES (1, ?, ?, ?, ?, ?)", 
                           (symbol, pos_type, price, qty, trailing_high))
        self.conn.commit()

    def get_active_pos(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM active_pos WHERE id = 1")
        return cursor.fetchone()

    def log_trade(self, symbol, signal_type, entry_price, exit_price, qty, pnl, total_pnl, 
                   direction="", market_context=None, is_exit=False):
        """詳細記錄每筆交易"""
        cursor = self.conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        context_str = json.dumps(market_context) if market_context else "{}"
        win_loss = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAK")
        
        cursor.execute("""INSERT INTO trades 
                         (timestamp, symbol, signal_type, entry_price, exit_price, qty, pnl, total_pnl, 
                          direction, win_loss, market_context) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (now_str, symbol, signal_type, entry_price, exit_price, qty, pnl, total_pnl,
                        direction, win_loss, context_str))
        
        # 更新信號勝率統計
        if is_exit:
            self._update_signal_stats(symbol, signal_type, pnl)
        
        self.conn.commit()
    
    def _update_signal_stats(self, symbol, signal_type, pnl):
        """更新信號成功率統計"""
        cursor = self.conn.cursor()
        cursor.execute("""SELECT * FROM signal_stats WHERE symbol = ? AND signal_type = ?""",
                       (symbol, signal_type))
        row = cursor.fetchone()
        
        if row:
            total = row['total_trades'] + 1
            wins = row['winning_trades'] + (1 if pnl > 0 else 0)
            losses = row['losing_trades'] + (1 if pnl < 0 else 0)
            win_rate = wins / total if total > 0 else 0
            avg_pnl = ((row['avg_pnl'] * row['total_trades']) + pnl) / total
            
            cursor.execute("""UPDATE signal_stats 
                             SET total_trades = ?, winning_trades = ?, losing_trades = ?, 
                                 win_rate = ?, avg_pnl = ?, last_updated = ?
                             WHERE symbol = ? AND signal_type = ?""",
                          (total, wins, losses, win_rate, avg_pnl, datetime.now(), symbol, signal_type))
        else:
            cursor.execute("""INSERT INTO signal_stats 
                             (symbol, signal_type, total_trades, winning_trades, losing_trades, win_rate, avg_pnl)
                             VALUES (?, ?, 1, ?, 0, ?, ?)""",
                          (symbol, signal_type, 1 if pnl > 0 else 0, 1.0 if pnl > 0 else 0.0, pnl))
        self.conn.commit()
    
    def get_signal_stats(self, symbol, signal_type):
        """獲取信號的勝率和性能統計"""
        cursor = self.conn.cursor()
        cursor.execute("""SELECT * FROM signal_stats WHERE symbol = ? AND signal_type = ?""",
                       (symbol, signal_type))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_range_summary(self, days):
        """取得指定天數內的交易摘要"""
        cursor = self.conn.cursor()
        time_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        # 僅計算平倉的損益
        cursor.execute("SELECT SUM(pnl), COUNT(id) FROM trades WHERE timestamp > ? AND pnl != 0", (time_limit,))
        res = cursor.fetchone()
        pnl = res[0] if res[0] else 0.0
        count = res[1] if res[1] else 0
        
        # 計算詳細統計
        cursor.execute("SELECT symbol, SUM(pnl) as total_pnl, COUNT(id) as count FROM trades WHERE timestamp > ? AND pnl != 0 GROUP BY symbol", (time_limit,))
        rows = cursor.fetchall()
        detailed = {}
        for row in rows:
            detailed[row['symbol']] = {'pnl': row['total_pnl'], 'trades': row['count']}
        
        return {'total_pnl': pnl, 'total_trades': count, 'detailed': detailed}

    def get_lifetime_summary(self):
        """取得生涯交易摘要"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT SUM(pnl), COUNT(id) FROM trades WHERE pnl != 0")
        res = cursor.fetchone()
        pnl = res[0] if res[0] else 0.0
        count = res[1] if res[1] else 0
        return pnl, count

    def get_latest_trades(self, limit=3):
        cursor = self.conn.cursor()
        cursor.execute("SELECT type, entry_price, exit_price, pnl, timestamp FROM trades WHERE type LIKE '%EXIT%' ORDER BY id DESC LIMIT ?", (limit,))
        return cursor.fetchall()

    def get_all_active_pos(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM active_pos")
        return cursor.fetchall()

    def get_detailed_stats(self, days=1, symbol=None):
        """取得詳細的交易統計"""
        cursor = self.conn.cursor()
        time_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        if symbol:
            cursor.execute("""SELECT COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
                                    COUNT(CASE WHEN pnl < 0 THEN 1 END) as losses,
                                    SUM(pnl) as total_pnl,
                                    AVG(pnl) as avg_pnl
                             FROM trades WHERE timestamp > ? AND symbol = ? AND pnl != 0""",
                          (time_limit, symbol))
        else:
            cursor.execute("""SELECT COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
                                    COUNT(CASE WHEN pnl < 0 THEN 1 END) as losses,
                                    SUM(pnl) as total_pnl,
                                    AVG(pnl) as avg_pnl
                             FROM trades WHERE timestamp > ? AND pnl != 0""",
                          (time_limit,))
        
        row = cursor.fetchone()
        if row:
            return {
                'long_win': row['wins'] // 2 if row['wins'] else 0,
                'long_loss': row['losses'] // 2 if row['losses'] else 0,
                'short_win': row['wins'] // 2 if row['wins'] else 0,
                'short_loss': row['losses'] // 2 if row['losses'] else 0,
                'total_pnl': row['total_pnl'] if row['total_pnl'] else 0,
                'avg_pnl': row['avg_pnl'] if row['avg_pnl'] else 0
            }
        return {'long_win': 0, 'long_loss': 0, 'short_win': 0, 'short_loss': 0, 'total_pnl': 0, 'avg_pnl': 0}
