# app/rl/env.py
import numpy as np
import pandas as pd
import mysql.connector
from app.rl.features import make_features, state_from_row

DB_CFG = dict(host="localhost", user="root", password="", database="trading_bot")

class TradingEnv:
    """Gym-like trading environment using data from market_bars."""
    def __init__(self, symbol: str, asset_type: str, window: int = 30, init_cash: float = 100_000):
        self.symbol = symbol
        self.asset_type = asset_type
        self.window = window
        self.init_cash = init_cash
        self._load_data()
        self.reset()

    def _load_data(self):
        cnx = mysql.connector.connect(**DB_CFG)
        cur = cnx.cursor(dictionary=True)
        cur.execute(
            """SELECT ts, open, high, low, close, volume
               FROM market_bars
               WHERE symbol=%s AND asset_type=%s
               ORDER BY ts ASC""",
            (self.symbol, self.asset_type),
        )
        rows = cur.fetchall()
        cur.close()
        cnx.close()
        df = pd.DataFrame(rows)
        if df.empty:
            raise RuntimeError(f"No bars found for {self.symbol} ({self.asset_type})")
        df.rename(columns=str.lower, inplace=True)
        self.df = make_features(df)

    def reset(self):
        self.t = self.window - 1
        self.position = 0
        self.cash = float(self.init_cash)
        self.equity = self.cash
        return self._get_state()

    def _get_state(self):
        cash_ratio = self.cash / self.equity if self.equity > 0 else 0
        return state_from_row(self.df, self.t, self.window, self.position, cash_ratio)

    def step(self, action: int):
        price = float(self.df.iloc[self.t]["close"])
        prev_equity = self.equity

        if action == 1 and self.cash >= price:
            self.position += 1
            self.cash -= price
        elif action == 2 and self.position > 0:
            self.position -= 1
            self.cash += price

        self.t += 1
        done = self.t >= len(self.df) - 1

        current_price = float(self.df.iloc[self.t]["close"])
        self.equity = self.cash + self.position * current_price
        reward = (self.equity - prev_equity) / max(prev_equity, 1e-9)
        return self._get_state(), reward, done, {"equity": self.equity, "price": current_price}

    def info(self):
        return dict(symbol=self.symbol, steps=len(self.df), window=self.window)
