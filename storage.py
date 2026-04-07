import sqlite3
from datetime import datetime

class Storage:
    def __init__(self, db_name="trading.db"):
        self.conn = sqlite3.connect(db_name)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # 交易紀錄：單筆損益、累積損益
        cursor.execute('''CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            type TEXT,
            price REAL,
            amount REAL,
            pnl REAL,
            cumulative_pnl REAL
        )''')
        # 訊號紀錄
        cursor.execute('''CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            signal TEXT,
            price REAL,
            rsi REAL,
            macd REAL
        )''')
        self.conn.commit()

    def log_signal(self, signal, price, rsi, macd):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO signals (timestamp, signal, price, rsi, macd) VALUES (?, ?, ?, ?, ?)",
                       (datetime.now().isoformat(), signal, price, rsi, macd))
        self.conn.commit()

    def log_trade(self, t_type, price, amount, pnl, cum_pnl):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO trades (timestamp, type, price, amount, pnl, cumulative_pnl) VALUES (?, ?, ?, ?, ?, ?)",
                       (datetime.now().isoformat(), t_type, price, amount, pnl, cum_pnl))
        self.conn.commit()

    def get_today_trades(self):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        # 查詢今天所有的買賣明細
        cursor.execute("""
            SELECT type, price, pnl, timestamp 
            FROM trades 
            WHERE timestamp LIKE ? 
            ORDER BY id ASC
        """, (f"{today}%",))
        return cursor.fetchall()

    def get_today_summary(self):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        # 統計今天結算的總損益 (只看賣出單的 pnl)
        cursor.execute("""
            SELECT COUNT(*), SUM(pnl) 
            FROM trades 
            WHERE timestamp LIKE ? AND type = 'SELL'
        """, (f"{today}%",))
        count, total_pnl = cursor.fetchone()
        return count or 0, total_pnl or 0.0

    def get_last_summary(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT cumulative_pnl FROM trades ORDER BY id DESC LIMIT 1")
            res = cursor.fetchone()
            return res[0] if res else 0
        except Exception:
            return 0


