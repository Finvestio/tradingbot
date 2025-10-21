from app.data.loader import load_market_data

df = load_market_data("AAPL", start="2024-01-01", end="2024-06-01")
print(df.tail(10))
