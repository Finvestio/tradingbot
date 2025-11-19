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
        """Load market data from database or API as fallback."""
        cnx = None
        cur = None
        try:
            # Try to load from database first
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
            if cur:
                cur.close()
            if cnx:
                cnx.close()
            
            if not rows:
                print(f"⚠️ No bars in database for {self.symbol}, fetching from API...")
                # Fallback to fresh API data (same as chart_data endpoint)
                from app.data.loader import fetch_from_api, load_market_data
                
                # Try API first
                try:
                    df = fetch_from_api(self.symbol, self.asset_type, interval="1day", outputsize=100)
                except Exception as api_error:
                    print(f"⚠️ API fetch failed: {api_error}")
                    print(f"📦 Trying cached data as fallback...")
                    # Fallback to cached data
                    df = load_market_data(self.symbol, self.asset_type)
                
                if df is None or df.empty:
                    raise RuntimeError(f"No data available for {self.symbol} ({self.asset_type})")
                
                print(f"✅ Fetched {len(df)} rows with columns: {list(df.columns)}")
                
                # Reset index to get Date as a column (it's currently the index)
                df = df.reset_index()
                
                # Rename columns to lowercase
                df.columns = df.columns.str.lower()
                
                # Map date to ts
                if 'date' in df.columns:
                    df = df.rename(columns={'date': 'ts'})
                
                # Ensure we have all required columns
                required_cols = ['ts', 'open', 'high', 'low', 'close', 'volume']
                if not all(col in df.columns for col in required_cols):
                    print(f"⚠️ Available columns: {list(df.columns)}")
                    raise RuntimeError(f"Missing required columns. Have: {list(df.columns)}, Need: {required_cols}")
                
                df = df[required_cols]
            else:
                df = pd.DataFrame(rows)
            
            df.rename(columns=str.lower, inplace=True)
            self.df = make_features(df)
            print(f"✅ Loaded {len(self.df)} bars for {self.symbol}")
            
        except Exception as e:
            print(f"❌ Error loading market data: {e}")
            import traceback
            traceback.print_exc()
            # Ensure cleanup on error
            if cur:
                cur.close()
            if cnx:
                cnx.close()
            raise RuntimeError(f"Failed to load data for {self.symbol} ({self.asset_type}): {e}")

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
        
        # Execute action and calculate reward
        reward = 0.0
        trade_executed = False
        
        if action == 1:  # BUY
            if self.cash >= price:
                self.position += 1
                self.cash -= price
                trade_executed = True
                # Small negative reward for the cost of trading
                reward -= 0.001  # Trading cost penalty
            else:
                # Penalty for trying to buy with insufficient funds
                reward = -0.01
                
        elif action == 2:  # SELL
            if self.position > 0:
                self.position -= 1
                self.cash += price
                trade_executed = True
                # Small negative reward for the cost of trading
                reward -= 0.001  # Trading cost penalty
            else:
                # Penalty for trying to sell without position
                reward = -0.01
        
        # Action 0 (HOLD) has no immediate cost
        
        self.t += 1
        done = self.t >= len(self.df) - 1
        
        current_price = float(self.df.iloc[self.t]["close"]) if not done else price
        new_equity = self.cash + self.position * current_price
        
        # Calculate equity change reward
        equity_change = new_equity - prev_equity
        
        if trade_executed:
            # For executed trades, reward is based on immediate impact + future price direction
            if action == 1:  # BUY
                # Reward buying if price goes up after purchase
                price_change = (current_price - price) / price if price > 0 else 0
                reward += price_change * 10  # Amplify price direction reward
            elif action == 2:  # SELL
                # Reward selling if price goes down after sale  
                price_change = (price - current_price) / price if price > 0 else 0
                reward += price_change * 10  # Amplify price direction reward
        else:
            # For HOLD, reward is proportional to portfolio performance
            reward += (new_equity - prev_equity) / max(prev_equity, 1e-9)
        
        self.equity = new_equity
        
        # Add small penalty for excessive trading to encourage quality trades
        if trade_executed and hasattr(self, 'recent_trades'):
            self.recent_trades = getattr(self, 'recent_trades', 0) + 1
            if self.recent_trades > 5:  # More than 5 trades recently
                reward -= 0.005  # Overtrading penalty
        else:
            self.recent_trades = max(0, getattr(self, 'recent_trades', 0) - 0.1)
        
        return self._get_state(), reward, done, {
            "equity": self.equity, 
            "price": current_price,
            "trade_executed": trade_executed
        }

    def info(self):
        return dict(symbol=self.symbol, steps=len(self.df), window=self.window)
