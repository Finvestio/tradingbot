import os
import requests
import pandas as pd
from app.database import SessionLocal
from app.models import MarketData
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TWELVEDATA_API_KEY", "f5206f280321485f9fe877095108faac")

def fetch_from_api(symbol: str) -> pd.DataFrame:
    """
    Fetches daily prices from Twelve Data free endpoint.
    Ensures proper datetime index for consistency.
    """
    print(f"📡 Fetching {symbol} data from Twelve Data ...")
    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={symbol}&interval=1day&outputsize=5000&apikey={API_KEY}"
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


def load_market_data(symbol: str, start=None, end=None) -> pd.DataFrame:
    with SessionLocal() as db:
        rows = db.query(MarketData).filter(MarketData.symbol == symbol).all()
        if rows:
            df = pd.DataFrame([(r.date, r.close) for r in rows], columns=["Date", "Close"])
            # Ensure Date column is datetime before setting as index
            df["Date"] = pd.to_datetime(df["Date"])
            df.set_index("Date", inplace=True)
            # Sort by date to ensure chronological order
            df.sort_index(inplace=True)
            print(f"💾 Loaded {len(df)} cached rows for {symbol}.")
            return df
    # Fetch then store
    df = fetch_from_api(symbol)
    save_to_db(symbol, df)
    return df
