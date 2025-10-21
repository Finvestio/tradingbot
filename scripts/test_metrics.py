from app.data.loader import load_market_data
from app.strategy.sma_cross import SmaCross
from app.backtest.metrics import compute_equity_curve, compute_metrics

# --- 1️⃣ Load real data via Alpha Vantage (or fallback) ---
symbol = "AAPL"
df = load_market_data(symbol)  # will use Alpha Vantage because key is in .env

print(f"\nData loaded for {symbol}: {len(df)} rows\n")

# --- 2️⃣ Apply SMA crossover strategy ---
strategy = SmaCross(fast=10, slow=20)
df["Signal"] = strategy.generate_signals(df)

# --- 3️⃣ Compute equity curve and metrics ---
equity = compute_equity_curve(df["Close"], df["Signal"])
stats = compute_metrics(equity)

# --- 4️⃣ Display results ---
print("Performance metrics:")
for k, v in stats.items():
    print(f"{k}: {v}")

print("\nLast 10 equity values:")
print(equity.tail(10))
