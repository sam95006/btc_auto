import sqlite3
from datetime import datetime, timedelta

import os

class Storage:
    def __init__(self, db_name="data/trading.db"):
        os.makedirs(os.path.dirname(db_name), exist_ok=True)
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.init_db()

    def init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            daily_pnl REAL,
            cumulative_pnl REAL
        )''')
        
        # 升級: 加入 entry_price 以利精確報表追蹤
        cursor.execute('''CREATE TABLE IF NOT EXISTS trades
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          timestamp TEXT, type TEXT, entry_price REAL, exit_price REAL, qty REAL, pnl REAL, total_pnl REAL)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS active_pos
                         (id INTEGER PRIMARY KEY, symbol TEXT, type TEXT, entry_price REAL, qty REAL, trailing_high REAL)''')
        
        # 3. 交易教訓記錄 (自我進化大腦用)
        cursor.execute('''CREATE TABLE IF NOT EXISTS lessons (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            pnl REAL,
                            reason TEXT,
                            market_context TEXT)''')
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

    def log_trade(self, type_str, exit_price, qty, pnl, total_pnl):
        # 如果是 EXIT，我們需要找倒最近一次的 ENTRY 價位
        cursor = self.conn.cursor()
        entry_price = 0.0
        if "EXIT" in type_str:
            cursor.execute("SELECT entry_price FROM trades WHERE type LIKE 'ENTRY%' ORDER BY id DESC LIMIT 1")
            res = cursor.fetchone()
            if res: entry_price = res[0]
        else: 
            # 如果是 ENTRY，entry 價格就是 current_price 傳進來的 (這裡在參數裡用 exit_price 暫代)
            entry_price = exit_price 

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO trades (timestamp, type, entry_price, exit_price, qty, pnl, total_pnl) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (now_str, type_str, entry_price, exit_price, qty, pnl, total_pnl))
        self.conn.commit()

    def get_range_summary(self, days):
        cursor = self.conn.cursor()
        time_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        # 僅計算平倉的損益
        cursor.execute("SELECT SUM(pnl), COUNT(id) FROM trades WHERE timestamp > ? AND type LIKE '%EXIT%'", (time_limit,))
        res = cursor.fetchone()
        pnl = res[0] if res[0] else 0.0
        count = res[1] if res[1] else 0
        return pnl, count

    def get_lifetime_summary(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT SUM(pnl), COUNT(id) FROM trades WHERE type LIKE '%EXIT%'")
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
        cursor = self.conn.cursor()
        time_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        query = "SELECT type, pnl, entry_price, qty FROM trades WHERE timestamp > ? AND type LIKE '%EXIT%'"
        params = [time_limit]
        if symbol:
            query += " AND type LIKE ?"
            params.append(f"%{symbol}%")
            
        cursor.execute(query, tuple(params))
        trades = cursor.fetchall()
        stats = {'long_win': 0, 'long_loss': 0, 'short_win': 0, 'short_loss': 0, 'total_volume': 0.0, 'total_pnl': 0.0}
        for t, pnl, ep, qty in trades:
            stats['total_pnl'] += pnl
            stats['total_volume'] += (ep * qty)
            if "LONG" in t:
                if pnl > 0: stats['long_win'] += 1
                else: stats['long_loss'] += 1
            else:
                if pnl > 0: stats['short_win'] += 1
                else: stats['short_loss'] += 1
        return stats
