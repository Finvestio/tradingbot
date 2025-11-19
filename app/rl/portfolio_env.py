# app/rl/portfolio_env.py
"""
Multi-asset portfolio trading environment.
Manages multiple assets simultaneously and optimizes portfolio-level decisions.
"""
import numpy as np
import pandas as pd
import mysql.connector
from typing import List, Dict, Tuple
from app.rl.features import make_features, state_from_row

DB_CFG = dict(host="localhost", user="root", password="", database="trading_bot")


class PortfolioEnv:
    """Multi-asset portfolio trading environment."""
    
    def __init__(self, symbols: List[Tuple[str, str]], window: int = 30, init_cash: float = 100_000):
        """
        Args:
            symbols: List of (symbol, asset_type) tuples, e.g., [("AAPL", "stock"), ("BTC/USD", "crypto")]
            window: Lookback window for state
            init_cash: Initial cash balance
        """
        self.symbols = symbols
        self.num_assets = len(symbols)
        self.window = window
        self.init_cash = init_cash
        
        # Load data for all assets
        self.asset_data = {}
        self._load_all_data()
        
        # Portfolio state
        self.reset()
    
    def _load_all_data(self):
        """Load market data for all assets."""
        cnx = None
        cur = None
        
        try:
            cnx = mysql.connector.connect(**DB_CFG)
            cur = cnx.cursor(dictionary=True)
            
            for symbol, asset_type in self.symbols:
                try:
                    # Try database first
                    cur.execute(
                        """SELECT ts, open, high, low, close, volume
                           FROM market_bars
                           WHERE symbol=%s AND asset_type=%s
                           ORDER BY ts ASC""",
                        (symbol, asset_type),
                    )
                    rows = cur.fetchall()
                    
                    if not rows:
                        # Fallback to API
                        print(f"⚠️ No bars in database for {symbol}, fetching from API...")
                        from app.data.loader import fetch_from_api, load_market_data
                        
                        try:
                            df = fetch_from_api(symbol, asset_type, interval="1day", outputsize=100)
                        except Exception:
                            df = load_market_data(symbol, asset_type)
                        
                        if df is None or df.empty:
                            raise RuntimeError(f"No data available for {symbol} ({asset_type})")
                        
                        df = df.reset_index()
                        df.columns = df.columns.str.lower()
                        if 'date' in df.columns:
                            df = df.rename(columns={'date': 'ts'})
                        
                        required_cols = ['ts', 'open', 'high', 'low', 'close', 'volume']
                        if not all(col in df.columns for col in required_cols):
                            raise RuntimeError(f"Missing required columns for {symbol}")
                        
                        df = df[required_cols]
                    else:
                        df = pd.DataFrame(rows)
                    
                    df.rename(columns=str.lower, inplace=True)
                    df = make_features(df)
                    self.asset_data[(symbol, asset_type)] = df
                    print(f"✅ Loaded {len(df)} bars for {symbol} ({asset_type})")
                    
                except Exception as e:
                    print(f"❌ Error loading data for {symbol}: {e}")
                    raise
        
        finally:
            if cur:
                cur.close()
            if cnx:
                cnx.close()
        
        # Align all dataframes to common timestamps
        self._align_data()
    
    def _align_data(self):
        """Align all asset data to common timestamps."""
        if not self.asset_data:
            return
        
        # Get intersection of all timestamps
        all_timestamps = None
        for df in self.asset_data.values():
            if all_timestamps is None:
                all_timestamps = set(df['ts'].values)
            else:
                all_timestamps = all_timestamps.intersection(set(df['ts'].values))
        
        if not all_timestamps:
            raise RuntimeError("No common timestamps across assets")
        
        all_timestamps = sorted(list(all_timestamps))
        
        # Filter and reindex all dataframes
        for key in self.asset_data:
            df = self.asset_data[key]
            df = df[df['ts'].isin(all_timestamps)].copy()
            df = df.sort_values('ts').reset_index(drop=True)
            self.asset_data[key] = df
        
        self.timestamps = all_timestamps
        print(f"✅ Aligned {len(self.timestamps)} common timestamps across {self.num_assets} assets")
    
    def reset(self):
        """Reset environment to initial state."""
        self.t = self.window - 1
        # Portfolio positions: {asset_key: quantity}
        self.positions = {key: 0 for key in self.asset_data.keys()}
        self.cash = float(self.init_cash)
        self.equity = self.cash
        self.initial_equity = self.cash
        
        # Portfolio history for metrics
        self.equity_history = [self.equity]
        self.returns_history = []
        
        return self._get_state()
    
    def _get_state(self) -> np.ndarray:
        """Build multi-asset portfolio state vector."""
        state_parts = []
        
        # For each asset, get its state
        for key in self.asset_data.keys():
            symbol, asset_type = key
            df = self.asset_data[key]
            
            # Get asset-specific state
            position = self.positions[key]
            cash_ratio = self.cash / max(self.equity, 1e-9)
            
            asset_state = state_from_row(df, self.t, self.window, position, cash_ratio)
            state_parts.append(asset_state)
        
        # Add portfolio-level features
        portfolio_features = self._get_portfolio_features()
        state_parts.append(portfolio_features)
        
        # Concatenate all states
        full_state = np.concatenate(state_parts).astype(np.float32)
        return full_state
    
    def _get_portfolio_features(self) -> np.ndarray:
        """Get portfolio-level features."""
        features = []
        
        # Portfolio value breakdown
        total_position_value = 0
        for key, quantity in self.positions.items():
            if quantity > 0:
                df = self.asset_data[key]
                current_price = float(df.iloc[self.t]["close"])
                total_position_value += quantity * current_price
        
        # Cash ratio
        features.append(self.cash / max(self.equity, 1e-9))
        
        # Position value ratio
        features.append(total_position_value / max(self.equity, 1e-9))
        
        # Number of positions
        num_positions = sum(1 for qty in self.positions.values() if qty > 0)
        features.append(num_positions / self.num_assets)  # Normalized
        
        # Portfolio diversification (entropy of positions)
        if self.equity > 0:
            position_weights = []
            for key, quantity in self.positions.items():
                if quantity > 0:
                    df = self.asset_data[key]
                    current_price = float(df.iloc[self.t]["close"])
                    position_value = quantity * current_price
                    position_weights.append(position_value / self.equity)
            
            if position_weights:
                position_weights = np.array(position_weights)
                position_weights = position_weights / position_weights.sum()
                # Shannon entropy (diversification measure)
                entropy = -np.sum(position_weights * np.log(position_weights + 1e-9))
                features.append(entropy / np.log(len(position_weights) + 1e-9))  # Normalized
            else:
                features.append(0.0)
        else:
            features.append(0.0)
        
        # Portfolio return (if we have history)
        if len(self.returns_history) > 0:
            recent_returns = self.returns_history[-10:] if len(self.returns_history) >= 10 else self.returns_history
            features.append(np.mean(recent_returns))  # Mean return
            features.append(np.std(recent_returns) if len(recent_returns) > 1 else 0.0)  # Volatility
        else:
            features.extend([0.0, 0.0])
        
        return np.array(features, dtype=np.float32)
    
    def step(self, actions: Dict[Tuple[str, str], int]) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Execute actions for all assets.
        
        Args:
            actions: Dict mapping (symbol, asset_type) -> action (0=HOLD, 1=BUY, 2=SELL)
        
        Returns:
            next_state, reward, done, info
        """
        prev_equity = self.equity
        total_reward = 0.0
        trades_executed = 0
        
        # Execute actions for each asset
        for key in self.asset_data.keys():
            if key not in actions:
                continue  # Skip if no action specified
            
            action = actions[key]
            symbol, asset_type = key
            df = self.asset_data[key]
            price = float(df.iloc[self.t]["close"])
            position = self.positions[key]
            
            asset_reward = 0.0
            trade_executed = False
            
            if action == 1:  # BUY
                if self.cash >= price:
                    self.positions[key] += 1
                    self.cash -= price
                    trade_executed = True
                    trades_executed += 1
                    asset_reward -= 0.001  # Trading cost
                else:
                    asset_reward = -0.01  # Insufficient funds penalty
            
            elif action == 2:  # SELL
                if position > 0:
                    self.positions[key] -= 1
                    self.cash += price
                    trade_executed = True
                    trades_executed += 1
                    asset_reward -= 0.001  # Trading cost
                else:
                    asset_reward = -0.01  # No position to sell
            
            total_reward += asset_reward
        
        # Move to next time step
        self.t += 1
        done = self.t >= len(self.timestamps) - 1
        
        # Calculate new equity (cash + all positions)
        new_equity = self.cash
        for key, quantity in self.positions.items():
            if quantity > 0:
                df = self.asset_data[key]
                current_price = float(df.iloc[self.t]["close"]) if not done else float(df.iloc[self.t - 1]["close"])
                new_equity += quantity * current_price
        
        # Portfolio-level reward
        equity_change = new_equity - prev_equity
        portfolio_return = equity_change / max(prev_equity, 1e-9)
        
        # Reward based on portfolio performance
        total_reward += portfolio_return * 10  # Amplify portfolio return
        
        # Diversification bonus (encourage holding multiple assets)
        num_positions = sum(1 for qty in self.positions.values() if qty > 0)
        if num_positions > 1:
            total_reward += 0.01 * (num_positions - 1) / self.num_assets  # Diversification bonus
        
        # Risk penalty (penalize high volatility)
        self.equity_history.append(new_equity)
        if len(self.equity_history) >= 10:
            recent_returns = np.diff(self.equity_history[-10:]) / np.array(self.equity_history[-10:-1])
            volatility = np.std(recent_returns)
            if volatility > 0.05:  # High volatility threshold
                total_reward -= 0.02 * (volatility - 0.05) / 0.05  # Risk penalty
        
        # Sharpe ratio bonus (reward risk-adjusted returns)
        if len(self.equity_history) >= 20:
            returns = np.diff(self.equity_history[-20:]) / np.array(self.equity_history[-20:-1])
            if len(returns) > 1 and np.std(returns) > 0:
                sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)  # Annualized Sharpe
                if sharpe > 0:
                    total_reward += 0.05 * min(sharpe / 2.0, 1.0)  # Sharpe bonus (capped)
        
        self.equity = new_equity
        self.returns_history.append(portfolio_return)
        
        info = {
            "equity": self.equity,
            "portfolio_return": portfolio_return,
            "trades_executed": trades_executed,
            "num_positions": num_positions,
            "cash": self.cash
        }
        
        return self._get_state(), total_reward, done, info
    
    def info(self):
        """Get environment information."""
        return {
            "symbols": self.symbols,
            "num_assets": self.num_assets,
            "timestamps": len(self.timestamps),
            "window": self.window
        }

