import os
import requests
import pandas as pd
from app.database import SessionLocal
from app.models import MarketData
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TWELVEDATA_API_KEY", "f5206f280321485f9fe877095108faac")

def fetch_from_api(symbol: str, asset_type: str = "stock", interval: str = "1day", outputsize: int = 5000) -> pd.DataFrame:
    """
    Fetches daily prices from Twelve Data free endpoint.
    Ensures proper datetime index for consistency.
    Supports different asset types.
    """
    print(f"📡 Fetching {symbol} ({asset_type}) data from Twelve Data ...")
    
    # Modify URL based on asset type
    if asset_type == "crypto":
        # For crypto, ensure we have the proper format
        if "/" not in symbol:
            symbol = f"{symbol}/USD"
        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={API_KEY}"
        )
    elif asset_type == "derivative":
        # For derivatives, use same logic or add specific handling
        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={API_KEY}"
        )
    else:  # stock
        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={API_KEY}"
        )
    
    r = requests.get(url)
    data = r.json()

    # Validate
    if "values" not in data:
        raise RuntimeError(data.get("message") or "Unexpected response")

    df = pd.DataFrame(data["values"])
    # Ensure datetime conversion is robust
    df["datetime"] = pd.to_datetime(df["datetime"], errors='coerce')
    df.rename(columns={"datetime": "Date", "close": "Close"}, inplace=True)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    
    # Remove any rows with invalid dates or prices
    df = df.dropna(subset=["Date", "Close"])
    
    # Sort by date and set as index
    df.sort_values("Date", inplace=True)
    df.set_index("Date", inplace=True)

    print(f"✅ Loaded {len(df)} rows from Twelve Data.")
    return df[["Close"]]


def save_to_db(symbol: str, df: pd.DataFrame):
    with SessionLocal() as db:
        for d, row in df.iterrows():
            date = pd.to_datetime(d).date()
            if not db.query(MarketData).filter_by(symbol=symbol, date=date).first():
                db.add(MarketData(symbol=symbol, date=date, close=float(row["Close"])))
        db.commit()


def load_market_data(symbol: str, asset_type: str = "stock", interval: str = "1day", outputsize: int = 5000, start=None, end=None) -> pd.DataFrame:
    """
    Load market data with support for different asset types
    """
    # Create a unique key for caching that includes asset type
    cache_key = f"{symbol}_{asset_type}" if asset_type != "stock" else symbol
    
    with SessionLocal() as db:
        rows = db.query(MarketData).filter(MarketData.symbol == cache_key).all()
        if rows:
            df = pd.DataFrame([(r.date, r.close) for r in rows], columns=["Date", "Close"])
            # Ensure Date column is datetime before setting as index
            df["Date"] = pd.to_datetime(df["Date"])
            df.set_index("Date", inplace=True)
            # Sort by date to ensure chronological order
            df.sort_index(inplace=True)
            print(f"💾 Loaded {len(df)} cached rows for {cache_key}.")
            return df
    # Fetch then store
    df = fetch_from_api(symbol, asset_type, interval, outputsize)
    save_to_db(cache_key, df)  # Save with cache_key to differentiate asset types
    return df
