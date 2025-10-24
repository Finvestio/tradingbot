import os, requests, pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

try:
    from app.database import SessionLocal
    from app.models import MarketData
except ImportError:
    # Fallback for direct imports
    from database import SessionLocal
    from models import MarketData

API_KEY = os.getenv("ALPHAVANTAGE_KEY", "P7FUY1D5FQ57V8Z8")

def fetch_from_api(symbol: str) -> pd.DataFrame:
    """Fetch market data from Alpha Vantage API"""
    print(f"Fetching {symbol} data from Alpha Vantage API...")
    url = (
        f"https://www.alphavantage.co/query?"
        f"function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=compact&apikey={API_KEY}"
    )
    r = requests.get(url)
    print("HTTP status:", r.status_code)
    json_data = r.json()

    if "Time Series (Daily)" not in json_data:
        raise RuntimeError(f"Invalid response for {symbol}: "
                           f"{json_data.get('Note') or json_data.get('Error Message') or 'unknown error'}")

    # Parse "Time Series (Daily)"
    data = pd.DataFrame(json_data["Time Series (Daily)"]).T
    data.index = pd.to_datetime(data.index)
    
    # Rename "4. close" → "Close"
    data = data.rename(columns={"4. close": "Close"})
    
    # Convert to numeric
    data["Close"] = pd.to_numeric(data["Close"], errors="coerce")
    
    # Sort by date
    data.sort_index(inplace=True)
    
    print(f"SUCCESS: Fetched {len(data)} rows for {symbol} from API")
    return data[["Close"]]

def save_to_db(symbol: str, df: pd.DataFrame):
    """Save DataFrame to MySQL database"""
    print(f"Saving {symbol} data to database...")
    session = SessionLocal()
    
    try:
        saved_count = 0
        for date_index, row in df.iterrows():
            # Check if record already exists
            existing = session.query(MarketData).filter(
                MarketData.symbol == symbol,
                MarketData.date == date_index.date()
            ).first()
            
            if not existing:
                # Insert new record
                market_data = MarketData(
                    symbol=symbol,
                    date=date_index.date(),
                    close=float(row['Close'])
                )
                session.add(market_data)
                saved_count += 1
        
        # Commit all changes
        session.commit()
        print(f"SUCCESS: Saved {saved_count} new records to database for {symbol}")
        
    except Exception as e:
        session.rollback()
        print(f"ERROR: Error saving to database: {e}")
        raise
    finally:
        session.close()

def load_market_data(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """Load market data from database first, fallback to API"""
    session = SessionLocal()
    
    try:
        # Try to load existing rows from MySQL first
        existing_data = session.query(MarketData).filter(
            MarketData.symbol == symbol
        ).order_by(MarketData.date).all()
        
        if existing_data:
            # Data exists → return as DataFrame with columns Date, Close
            print(f"Loading {symbol} data from database cache...")
            data = []
            for record in existing_data:
                data.append({
                    'Date': record.date,
                    'Close': record.close
                })
            
            df = pd.DataFrame(data)
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            print(f"SUCCESS: Loaded {len(df)} rows for {symbol} from database")
            return df[["Close"]]
            
        else:
            # No data exists → fetch from API, save to DB, then return
            print(f"No cached data found for {symbol}, fetching from API...")
            df = fetch_from_api(symbol)
            save_to_db(symbol, df)
            
            # Convert index to Date column for consistency
            result_df = df.copy()
            result_df.reset_index(inplace=True)
            result_df.rename(columns={'index': 'Date'}, inplace=True)
            result_df.set_index('Date', inplace=True)
            
            return result_df[["Close"]]
            
    finally:
        session.close()
