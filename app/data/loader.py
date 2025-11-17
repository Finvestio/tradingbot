import os
import requests
import pandas as pd
from app.database import SessionLocal
from app.models import MarketData
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TWELVEDATA_API_KEY", "f5206f280321485f9fe877095108faac")

def fetch_realtime_price(symbol: str, asset_type: str = "stock") -> dict:
    """
    Fetches real-time price quote from Twelve Data API.
    Returns current price, volume, and other quote data.
    """
    
    # Modify symbol for crypto
    query_symbol = symbol
    if asset_type == "crypto" and "/" not in symbol:
        query_symbol = f"{symbol}/USD"
    
    # Use price endpoint for real-time data
    url = f"https://api.twelvedata.com/price?symbol={query_symbol}&apikey={API_KEY}"
    
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Check for API errors
        if "code" in data and data.get("code") != 200:
            error_msg = data.get("message", "Unknown API error")
            raise RuntimeError(f"API Error: {error_msg}")
        
        # Validate response structure
        if "price" not in data:
            error_msg = data.get("message", "Unexpected response format")
            raise RuntimeError(f"Invalid response: {error_msg}")
        
        return {
            "symbol": symbol,
            "price": float(data.get("price", 0)),
            "timestamp": data.get("timestamp", datetime.now().isoformat()),
            "volume": int(data.get("volume", 0)) if data.get("volume") else 0
        }
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error: {str(e)}")
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"Data parsing error: {str(e)}")

def fetch_from_api(symbol: str, asset_type: str = "stock", interval: str = "1day", outputsize: int = 5000) -> pd.DataFrame:
    """
    Fetches historical prices from Twelve Data free endpoint.
    Ensures proper datetime index for consistency.
    Supports different asset types.
    """
    
    # Modify symbol for crypto
    query_symbol = symbol
    if asset_type == "crypto":
        if "/" not in symbol:
            query_symbol = f"{symbol}/USD"
    
    # Build URL
    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={query_symbol}&interval={interval}&outputsize={outputsize}&apikey={API_KEY}"
    )
    
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        # Check for API errors
        if "code" in data and data.get("code") != 200:
            error_msg = data.get("message", "Unknown API error")
            print(f"❌ Twelve Data API error: {error_msg}")
            raise RuntimeError(f"API Error: {error_msg}")
        
        # Validate response has values
        if "values" not in data:
            error_msg = data.get("message", "Unexpected response format")
            print(f"❌ Invalid response: {error_msg}")
            print(f"   Response keys: {list(data.keys())}")
            raise RuntimeError(f"Invalid response: {error_msg}")

        df = pd.DataFrame(data["values"])
        
        # Check if DataFrame is empty
        if df.empty:
            raise RuntimeError(f"No data returned for {symbol}")
        
        # Ensure datetime conversion is robust
        df["datetime"] = pd.to_datetime(df["datetime"], errors='coerce')
        
        # Rename columns to standard format
        column_mapping = {
            "datetime": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        }
        
        # Rename only columns that exist
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)
        
        # Convert numeric columns
        numeric_cols = ["Open", "High", "Low", "Close", "Volume"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # Remove any rows with invalid dates or close prices
        df = df.dropna(subset=["Date", "Close"])
        
        if df.empty:
            raise RuntimeError(f"No valid data after processing for {symbol}")
        
        # Sort by date and set as index
        df.sort_values("Date", inplace=True)
        df.set_index("Date", inplace=True)

        # Return all available columns (at minimum Close, but prefer all OHLCV)
        available_cols = [col for col in ["Open", "High", "Low", "Close", "Volume"] if col in df.columns]
        if not available_cols:
            available_cols = ["Close"]  # Fallback to Close only
        
        print(f"✅ Loaded {len(df)} rows from Twelve Data with columns: {available_cols}")
        return df[available_cols]
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching data: {e}")
        raise RuntimeError(f"Network error: {str(e)}")
    except (ValueError, KeyError) as e:
        print(f"❌ Data parsing error: {e}")
        raise RuntimeError(f"Data parsing error: {str(e)}")


def save_to_db(symbol: str, df: pd.DataFrame):
    """
    Save market data to database. Only saves Close price as that's what MarketData model stores.
    """
    with SessionLocal() as db:
        for d, row in df.iterrows():
            date = pd.to_datetime(d).date()
            if not db.query(MarketData).filter_by(symbol=symbol, date=date).first():
                close_price = float(row.get("Close", 0))
                if close_price > 0:  # Only save valid prices
                    db.add(MarketData(symbol=symbol, date=date, close=close_price))
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
