import sqlite3
from datetime import datetime, timedelta
import os
import json

class Storage:
    def __init__(self, db_name="trading.db"):
        """
        初始化存儲系統 - 所有交易、學習、失敗數據都保存到 Zeabur 持久硬碟
        
        數據持久化路徑優先級：
        1. /app/data ← Zeabur 持久硬碟（最優選擇）
        2. /data     ← Zeabur 備用持久卷
        3. ./        ← 本地開發環境
        """
        
        # 【Zeabur 持久硬碟】優先使用 /app/data
        zeabur_disk_path = "/app/data"
        zeabur_volume_path = "/data"
        local_path = os.getcwd()
        
        # 檢測可用的持久化路徑
        if os.path.exists(zeabur_disk_path) and os.access(zeabur_disk_path, os.W_OK):
            base_path = zeabur_disk_path
            storage_type = "Zeabur 持久硬碟 (/app/data)"
        elif os.path.exists(zeabur_volume_path) and os.access(zeabur_volume_path, os.W_OK):
            base_path = zeabur_volume_path
            storage_type = "Zeabur 持久卷 (/data)"
        else:
            base_path = local_path
            storage_type = "本地開發環境"
        
        # 確保目錄存在
        try:
            os.makedirs(base_path, exist_ok=True)
        except Exception as e:
            print(f"⚠️ 目錄創建失敗: {e}")
            base_path = local_path
        
        # 完整路徑
        self.db_path = os.path.join(base_path, db_name)
        print(f"""
╔════════════════════════════════════════╗
  🗄️  數據持久化系統
╚════════════════════════════════════════╝
📍 存儲類型: {storage_type}
📍 數據庫路徑: {self.db_path}
📊 用途: 交易記錄 + AI 學習 + 失敗分析
""")
        
        # 連接數據庫 (自動創建)
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # 返回字典格式
            print(f"✅ 數據庫連接成功")
        except Exception as e:
            print(f"❌ 數據庫連接失敗: {e}")
            raise
        
        self.init_db()

    def backup_database(self):
        """
        自動備份數據庫到時間戳文件
        用途: 防止誤刪或損壞，允許回滾
        """
        try:
            backup_dir = os.path.dirname(self.db_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"trading_backup_{timestamp}.db")
            
            # SQLite 備份方法
            backup_conn = sqlite3.connect(backup_path)
            self.conn.backup(backup_conn)
            backup_conn.close()
            
            print(f"✅ 數據庫備份成功: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"⚠️ 數據庫備份失敗: {e}")
            return None
    
    def verify_database_integrity(self):
        """驗證數據庫完整性"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            
            if result == "ok":
                print(f"✅ 數據庫完整性檢查通過")
                return True
            else:
                print(f"❌ 數據庫損壞: {result}")
                return False
        except Exception as e:
            print(f"⚠️ 完整性檢查失敗: {e}")
            return False

    def init_db(self):
        """初始化資料表與遷移邏輯"""
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            daily_pnl REAL,
            cumulative_pnl REAL
        )''')

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

        # 🔧 數據庫遷移: 確保舊表包含必要的欄位
        try:
            cursor.execute("PRAGMA table_info(trades)")
            existing_columns = {col[1] for col in cursor.fetchall()}
            required_columns = {
                'symbol': 'TEXT DEFAULT ""',
                'signal_type': 'TEXT DEFAULT ""',
                'entry_price': 'REAL DEFAULT 0',
                'exit_price': 'REAL DEFAULT 0',
                'qty': 'REAL DEFAULT 0',
                'pnl': 'REAL DEFAULT 0',
                'total_pnl': 'REAL DEFAULT 0',
                'direction': 'TEXT DEFAULT ""',
                'win_loss': 'TEXT DEFAULT "BREAK"',
                'market_context': 'TEXT DEFAULT "{}"'
            }
            for col_name, col_def in required_columns.items():
                if col_name not in existing_columns:
                    print(f"⚠️ 數據庫遷移: 添加缺失欄位 {col_name} 到 trades 表...")
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_def}")
        except Exception as e:
            print(f"⚠️ 數據庫遷移檢查失敗: {e}")

        cursor.execute('''CREATE TABLE IF NOT EXISTS active_pos
                         (id INTEGER PRIMARY KEY, symbol TEXT, type TEXT, entry_price REAL, qty REAL, trailing_high REAL)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS lessons (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            pnl REAL,
                            reason TEXT,
                            market_context TEXT,
                            signal_type TEXT,
                            is_learned INTEGER DEFAULT 0)''')

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

        cursor.execute('''CREATE TABLE IF NOT EXISTS global_config (
                            key TEXT PRIMARY KEY,
                            value TEXT)''')

        self.conn.commit()

    def close(self):
        """安全關閉數據庫連接"""
        try:
            if hasattr(self, 'conn') and self.conn:
                self.conn.commit()
                self.conn.close()
                print("✅ 數據庫已安全關閉")
        except Exception as e:
            print(f"⚠️ 關閉數據庫時出錯: {e}")

    def __del__(self):
        """析構時確保數據庫被安全保存"""
        try:
            if hasattr(self, 'conn') and self.conn:
                self.conn.commit()
                self.conn.close()
        except Exception:
            pass

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
    
    def get_all_signal_stats(self, symbol=None):
        """獲取所有信號統計"""
        cursor = self.conn.cursor()
        if symbol:
            cursor.execute("""SELECT * FROM signal_stats WHERE symbol = ? ORDER BY win_rate DESC""", (symbol,))
        else:
            cursor.execute("""SELECT * FROM signal_stats ORDER BY win_rate DESC""")
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows] if rows else []
    
    def get_today_trades(self, symbol=None):
        """獲取今日交易"""
        cursor = self.conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        
        if symbol:
            cursor.execute("""SELECT * FROM trades WHERE symbol = ? AND timestamp LIKE ? ORDER BY timestamp DESC""",
                          (symbol, f"{today}%"))
        else:
            cursor.execute("""SELECT * FROM trades WHERE timestamp LIKE ? ORDER BY timestamp DESC""",
                          (f"{today}%",))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows] if rows else []
    
    def get_symbol_performance(self, symbol, days=7):
        """獲取幣種性能統計"""
        cursor = self.conn.cursor()
        time_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        # 先檢查 win_loss 列是否存在
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]
        has_win_loss = 'win_loss' in columns
        
        if has_win_loss:
            cursor.execute("""SELECT 
                              COUNT(*) as total_trades,
                              COUNT(CASE WHEN win_loss = 'WIN' THEN 1 END) as win_count,
                              COUNT(CASE WHEN win_loss = 'LOSS' THEN 1 END) as loss_count,
                              SUM(pnl) as total_pnl,
                              AVG(pnl) as avg_pnl,
                              MAX(pnl) as max_pnl,
                              MIN(pnl) as min_pnl
                             FROM trades WHERE symbol = ? AND timestamp > ? AND pnl != 0""",
                           (symbol, time_limit))
        else:
            # 舊表: 用 pnl > 0 判斷勝負
            cursor.execute("""SELECT 
                              COUNT(*) as total_trades,
                              COUNT(CASE WHEN pnl > 0 THEN 1 END) as win_count,
                              COUNT(CASE WHEN pnl < 0 THEN 1 END) as loss_count,
                              SUM(pnl) as total_pnl,
                              AVG(pnl) as avg_pnl,
                              MAX(pnl) as max_pnl,
                              MIN(pnl) as min_pnl
                             FROM trades WHERE symbol = ? AND timestamp > ? AND pnl != 0""",
                           (symbol, time_limit))
        
        row = cursor.fetchone()
        if row:
            total = row['total_trades']
            wins = row['win_count']
            win_rate = (wins / total * 100) if total > 0 else 0
            return {
                'symbol': symbol,
                'total_trades': total,
                'wins': wins,
                'losses': row['loss_count'],
                'win_rate': f"{win_rate:.1f}%",
                'total_pnl': row['total_pnl'] if row['total_pnl'] else 0,
                'avg_pnl': row['avg_pnl'] if row['avg_pnl'] else 0,
                'max_pnl': row['max_pnl'] if row['max_pnl'] else 0,
                'min_pnl': row['min_pnl'] if row['min_pnl'] else 0
            }
        return None
    
    def get_best_signals(self, days=7):
        """獲取最佳表現的信號"""
        cursor = self.conn.cursor()
        cursor.execute("""SELECT * FROM signal_stats 
                         WHERE last_updated > datetime('now', '-' || ? || ' days')
                         ORDER BY win_rate DESC LIMIT 10""", (days,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows] if rows else []
    
    def get_worst_signals(self, days=7):
        """獲取最差表現的信號"""
        cursor = self.conn.cursor()
        cursor.execute("""SELECT * FROM signal_stats 
                         WHERE last_updated > datetime('now', '-' || ? || ' days')
                         ORDER BY win_rate ASC LIMIT 10""", (days,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows] if rows else []

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
        cursor.execute("SELECT signal_type, entry_price, exit_price, pnl, timestamp FROM trades WHERE signal_type LIKE '%EXIT%' ORDER BY id DESC LIMIT ?", (limit,))
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
    
    def get_symbol_trades(self, symbol, days=7):
        """
        【為 PerformanceOptimizer 獲取交易】
        返回過去 N 天特定幣種的所有交易
        每筆交易返回 (id, timestamp, symbol, signal_type, entry_price, pnl, ...)
        """
        cursor = self.conn.cursor()
        time_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""SELECT 
                          id, timestamp, symbol, signal_type, entry_price, 
                          exit_price, qty, pnl, total_pnl, direction, win_loss, market_context
                         FROM trades 
                         WHERE symbol = ? AND timestamp > ? AND pnl != 0
                         ORDER BY timestamp DESC""",
                       (symbol, time_limit))
        
        rows = cursor.fetchall()
        # 轉換為列表格式，便於 PerformanceOptimizer 遍歷
        trades = []
        for row in rows:
            trades.append((
                row['id'],
                row['timestamp'],
                row['symbol'],
                row['signal_type'],
                row['entry_price'],
                row['pnl'],  # 重要: pnl 在位置 5
                row['direction'],
                row['win_loss'],
                row['market_context']
            ))
        
        return trades

    def save_global_config(self, key, value):
        """保存全局配置/全局變數"""
        cursor = self.conn.cursor()
        cursor.execute("REPLACE INTO global_config (key, value) VALUES (?, ?)", (key, str(value)))
        self.conn.commit()

    def get_global_config(self, key, default=None):
        """讀取全局配置/全局變數"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM global_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

    def get_agent_history(self, symbol, limit=5):
        """獲取特定幣種的近期交易歷史與背景"""
        cursor = self.conn.cursor()
        cursor.execute("""SELECT timestamp, signal_type, pnl, market_context FROM trades 
                         WHERE symbol LIKE ? AND pnl != 0 
                         ORDER BY id DESC LIMIT ?""", (f"%{symbol}%", limit))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
