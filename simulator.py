import json
import os
from datetime import datetime

class Simulator:
    def __init__(self, initial_cash=10000, storage_file="trading_history.json"):
        self.storage_file = storage_file
        self.load_state(initial_cash)

    def load_state(self, initial_cash):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    self.cash = data.get('cash', initial_cash)
                    self.holdings = data.get('holdings', 0)
                    self.history = data.get('history', [])
            except:
                self.cash = initial_cash
                self.holdings = 0
                self.history = []
        else:
            self.cash = initial_cash
            self.holdings = 0
            self.history = []

    def save_state(self):
        with open(self.storage_file, 'w') as f:
            json.dump({
                'cash': self.cash,
                'holdings': self.holdings,
                'history': self.history
            }, f, indent=4)

    def buy(self, price, amount_usd, timestamp=None):
        if amount_usd > self.cash:
            amount_usd = self.cash
        
        if amount_usd <= 0:
            return None

        qty = amount_usd / price
        self.cash -= amount_usd
        self.holdings += qty
        
        trade = {
            'timestamp': timestamp or datetime.now().isoformat(),
            'type': 'BUY',
            'price': price,
            'amount_usd': amount_usd,
            'qty': qty,
            'remaining_cash': self.cash
        }
        self.history.append(trade)
        self.save_state()
        return trade

    def sell(self, price, qty=None, timestamp=None):
        if qty is None or qty > self.holdings:
            qty = self.holdings
        
        if qty <= 0:
            return None

        amount_usd = qty * price
        self.cash += amount_usd
        self.holdings -= qty
        
        trade = {
            'timestamp': timestamp or datetime.now().isoformat(),
            'type': 'SELL',
            'price': price,
            'amount_usd': amount_usd,
            'qty': qty,
            'remaining_cash': self.cash
        }
        self.history.append(trade)
        self.save_state()
        return trade

    def get_net_worth(self, current_price):
        return self.cash + (self.holdings * current_price)

    def get_daily_report(self, current_price):
        net_worth = self.get_net_worth(current_price)
        return {
            'cash': round(self.cash, 2),
            'holdings_btc': round(self.holdings, 6),
            'net_worth': round(net_worth, 2),
            'trade_count': len(self.history)
        }
