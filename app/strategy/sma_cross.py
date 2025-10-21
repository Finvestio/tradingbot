import pandas as pd
from .base import Strategy

class SmaCross(Strategy):
    """Simple moving-average crossover strategy."""
    def __init__(self, fast: int = 10, slow: int = 20):
        self.fast = fast
        self.slow = slow

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        # Ensure required column
        if "Close" not in df.columns:
            raise ValueError("DataFrame must contain a 'Close' column")

        fast_ma = df["Close"].rolling(self.fast).mean()
        slow_ma = df["Close"].rolling(self.slow).mean()

        # +1 = buy, -1 = sell, 0 = hold
        signals = (fast_ma > slow_ma).astype(int) - (fast_ma < slow_ma).astype(int)
        return signals.shift(1).fillna(0)
