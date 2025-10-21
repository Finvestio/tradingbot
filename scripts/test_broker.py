from app.data.loader import load_market_data
from app.strategy.sma_cross import SmaCross
from app.broker.simulator import SimBroker

# Load data
df = load_market_data("AAPL", start="2024-01-01", end="2024-06-01")

# Generate signals
strategy = SmaCross(fast=10, slow=20)
df["Signal"] = strategy.generate_signals(df)

# Simulate
broker = SimBroker(cash=100000)

for date, row in df.iterrows():
    signal = int(row["Signal"])
    price = row["Close"]
    broker.trade(price, signal, qty=10)
    broker.update_equity(price)

print("Final summary:")
print(broker.summary())
