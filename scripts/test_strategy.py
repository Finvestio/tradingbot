import pandas as pd
import yfinance as yf
from app.strategy.sma_cross import SmaCross

# Try to download Yahoo data
print("Loading data...")
data = yf.download("AAPL", start="2024-01-01", end="2024-06-01", progress=False)

# If data empty, load local CSV
if data.empty:
    print("Yahoo Finance unavailable — using local sample data.")
    data = pd.read_csv("app/data/sample.csv", parse_dates=["Date"], index_col="Date")

# Keep only Close column
data = data[["Close"]]

# Run strategy
strategy = SmaCross(fast=3, slow=5)
signals = strategy.generate_signals(data)

print("Last 10 signals:")
print(signals.tail(10))
