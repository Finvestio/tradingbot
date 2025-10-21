import os, requests, pandas as pd

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "P7FUY1D5FQ57V8Z8")

def load_market_data(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    print(f"Loading {symbol} data from Alpha Vantage (free endpoint)...")
    url = (
        f"https://www.alphavantage.co/query?"
        f"function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=compact&apikey={API_KEY}"
    )
    r = requests.get(url)
    print("HTTP status:", r.status_code)
    json_data = r.json()
    print("🔍 Response keys:", json_data.keys())

    if "Time Series (Daily)" not in json_data:
        raise RuntimeError(f"Invalid response for {symbol}: "
                           f"{json_data.get('Note') or json_data.get('Error Message') or 'unknown error'}")

    data = pd.DataFrame(json_data["Time Series (Daily)"]).T
    data.index = pd.to_datetime(data.index)
    data = data.rename(columns={"4. close": "Close"})
    data["Close"] = pd.to_numeric(data["Close"], errors="coerce")
    data.sort_index(inplace=True)
    print(f"✅ Loaded {len(data)} rows for {symbol}")
    return data[["Close"]]
