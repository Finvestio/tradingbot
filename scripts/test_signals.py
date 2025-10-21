from app.data.loader import load_market_data
from app.strategy.sma_cross import SmaCross

# 1. Load real market data
df = load_market_data("AAPL", start="2024-01-01", end="2024-06-01")

# 2. Apply SMA crossover strategy
strategy = SmaCross(fast=10, slow=20)
signals = strategy.generate_signals(df)

# 3. Combine both for easy reading
df["Signal"] = signals

# 4. Show tail
print(df.tail(15))
