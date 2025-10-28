from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.data.loader import load_market_data
import pandas as pd
import os, requests
from fastapi import Query
from dotenv import load_dotenv
import os

# Use relative imports when running as module, absolute when standalone
try:
    from .data.loader import load_market_data
    from .backtest.metrics import compute_equity_curve, compute_metrics
    from .api_orders import router as orders_router
except ImportError:
    from data.loader import load_market_data
    from backtest.metrics import compute_equity_curve, compute_metrics
    from api_orders import router as orders_router

app = FastAPI(title="Trading Bot API")

# Register the orders router
app.include_router(orders_router)

# -------------------------------------------------------------
# CORS configuration
# -------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# Root endpoint
# -------------------------------------------------------------
@app.get("/api/test_twelvedata")
def test_twelvedata(symbol: str = Query("AAPL")):
    key = os.getenv("TWELVEDATA_API_KEY")
    if not key:
        return {"error": "Missing TWELVEDATA_API_KEY in .env"}
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1day&outputsize=30&apikey={key}"
    r = requests.get(url)
    return r.json()
@app.get("/")
def root():
    return {"message": "Trading Bot API is running."}

# -------------------------------------------------------------
# Asset symbols configuration endpoint
# -------------------------------------------------------------
@app.get("/api/asset-symbols")
def get_asset_symbols():
    """
    Get available symbols by asset type for frontend dropdowns
    """
    return {
        "stock": [
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "GOOGL", "name": "Alphabet Inc."},
            {"symbol": "MSFT", "name": "Microsoft Corp."},
            {"symbol": "TSLA", "name": "Tesla Inc."},
            {"symbol": "AMZN", "name": "Amazon.com Inc."},
            {"symbol": "NVDA", "name": "NVIDIA Corp."},
            {"symbol": "META", "name": "Meta Platforms Inc."},
            {"symbol": "NFLX", "name": "Netflix Inc."},
            {"symbol": "AMD", "name": "Advanced Micro Devices"},
            {"symbol": "ORCL", "name": "Oracle Corp."}
        ],
        "crypto": [
            {"symbol": "BTC/USD", "name": "Bitcoin"},
            {"symbol": "ETH/USD", "name": "Ethereum"},
            {"symbol": "ADA/USD", "name": "Cardano"},
            {"symbol": "SOL/USD", "name": "Solana"},
            {"symbol": "DOT/USD", "name": "Polkadot"},
            {"symbol": "AVAX/USD", "name": "Avalanche"},
            {"symbol": "MATIC/USD", "name": "Polygon"},
            {"symbol": "LINK/USD", "name": "Chainlink"},
            {"symbol": "UNI/USD", "name": "Uniswap"},
            {"symbol": "ATOM/USD", "name": "Cosmos"}
        ],
        "derivative": [
            {"symbol": "SPY", "name": "SPDR S&P 500 ETF"},
            {"symbol": "QQQ", "name": "Invesco QQQ Trust"},
            {"symbol": "VIX", "name": "CBOE Volatility Index"},
            {"symbol": "GLD", "name": "SPDR Gold Shares"},
            {"symbol": "TLT", "name": "iShares 20+ Year Treasury"},
            {"symbol": "IWM", "name": "iShares Russell 2000"},
            {"symbol": "EFA", "name": "iShares MSCI EAFE"},
            {"symbol": "EEM", "name": "iShares MSCI Emerging"},
            {"symbol": "XLE", "name": "Energy Select Sector"},
            {"symbol": "XLF", "name": "Financial Select Sector"}
        ]
    }

# -------------------------------------------------------------
# Run trading strategy endpoint
# -------------------------------------------------------------
@app.post("/api/run_strategy")
def run_strategy(payload: dict):
    """
    Run trading simulation for a given symbol and parameters.
    Example payload:
    {"symbol": "AAPL", "fast": 10, "slow": 20}
    """
    symbol = payload.get("symbol")
    fast = int(payload.get("fast", 10))
    slow = int(payload.get("slow", 20))

    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    # Load market data
    try:
        df = load_market_data(symbol)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No market data found for symbol {symbol}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ---------------------------------------------------------
    # Ensure datetime index and create Date column properly
    # ---------------------------------------------------------
    # Make sure index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    
    # Create Date column from index
    df = df.copy()  # Avoid SettingWithCopyWarning
    df["Date"] = pd.to_datetime(df.index)

    # ---------------------------------------------------------
    # Simple SMA crossover strategy with proper logic
    # ---------------------------------------------------------
    df["SMA_fast"] = df["Close"].rolling(fast).mean()
    df["SMA_slow"] = df["Close"].rolling(slow).mean()
    df["Signal"] = 0
    df.loc[df["SMA_fast"] > df["SMA_slow"], "Signal"] = 1
    df.loc[df["SMA_fast"] < df["SMA_slow"], "Signal"] = -1

    # Compute equity curve and metrics
    equity_curve = compute_equity_curve(df["Close"], df["Signal"])
    metrics = compute_metrics(equity_curve)

    # ---------------------------------------------------------
    # Prepare the last 10 equity points for frontend with proper date formatting
    # ---------------------------------------------------------
    equity_df = equity_curve.tail(10).reset_index()
    equity_df.columns = ["Date", "Equity"]
    # Convert Date to datetime if not already
    equity_df["Date"] = pd.to_datetime(equity_df["Date"])
    # Format Date as string
    equity_df["Date"] = equity_df["Date"].dt.strftime("%Y-%m-%d")
    equity_df["Equity"] = equity_df["Equity"].astype(float)

    # ---------------------------------------------------------
    # Prepare recent price and signal data for frontend
    # ---------------------------------------------------------
    recent_df = df[["Date", "Close", "SMA_fast", "SMA_slow", "Signal"]].tail(20).copy()
    recent_df["Date"] = recent_df["Date"].dt.strftime("%Y-%m-%d")
    
    result = {
        "symbol": symbol,
        "metrics": metrics,
        "equity": equity_df.to_dict(orient="records"),
        "recent_data": recent_df.to_dict(orient="records")
    }

    return result


# -------------------------------------------------------------
# Get trading signals endpoint
# -------------------------------------------------------------
@app.get("/api/signals")
def get_signals(symbol: str, fast: int = 10, slow: int = 20):
    """
    Get trading signals for a given symbol and SMA parameters.
    Returns JSON array format: [{"Date": "2024-05-01", "Close": 189.3, "Signal": 1}]
    
    Parameters:
    - symbol: Stock symbol (e.g., "AAPL")
    - fast: Fast SMA window size (default: 10)
    - slow: Slow SMA window size (default: 20)
    """
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    # Load market data
    try:
        df = load_market_data(symbol)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No market data found for symbol {symbol}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ---------------------------------------------------------
    # Ensure datetime index and create Date column properly
    # ---------------------------------------------------------
    # Make sure index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    
    # Create Date column from index
    df = df.copy()  # Avoid SettingWithCopyWarning
    df["Date"] = pd.to_datetime(df.index)

    # ---------------------------------------------------------
    # Compute SMAs and signals with proper logic
    # ---------------------------------------------------------
    df["SMA_fast"] = df["Close"].rolling(fast).mean()
    df["SMA_slow"] = df["Close"].rolling(slow).mean()
    
    # Create Signal column
    df["Signal"] = 0
    df.loc[df["SMA_fast"] > df["SMA_slow"], "Signal"] = 1
    df.loc[df["SMA_fast"] < df["SMA_slow"], "Signal"] = -1

    # ---------------------------------------------------------
    # Prepare the last 20 rows with required columns and proper date formatting
    # ---------------------------------------------------------
    result_df = df[["Date", "Close", "SMA_fast", "SMA_slow", "Signal"]].tail(20).copy()
    
    # Ensure Date is datetime and format as string
    result_df["Date"] = pd.to_datetime(result_df["Date"])
    result_df["Date"] = result_df["Date"].dt.strftime("%Y-%m-%d")
    
    # Convert to the requested JSON array format
    signals_array = result_df.to_dict(orient="records")
    
    return signals_array

@app.get("/api/market_data")
async def get_market_data(symbol: str):
    """
    Get cached market data for a symbol from MySQL database
    """
    try:
        df = load_market_data(symbol)
        
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No market data found for symbol {symbol}")
        
        # Reset index to make sure Date is a column
        if df.index.name == 'Date' or 'Date' not in df.columns:
            df = df.reset_index()
        
        # Convert DataFrame to list of dictionaries
        market_data = []
        for _, row in df.iterrows():
            # Handle date field - it might be in different formats
            date_val = row.get('Date', row.name if hasattr(row, 'name') else None)
            if pd.isna(date_val):
                continue
                
            # Convert date to string format
            if hasattr(date_val, 'strftime'):
                date_str = date_val.strftime('%Y-%m-%d')
            else:
                date_str = str(date_val)
            
            market_data.append({
                "symbol": symbol.upper(),
                "date": date_str,
                "open": float(row.get('Open', row.get('open', 0))),
                "high": float(row.get('High', row.get('high', 0))),
                "low": float(row.get('Low', row.get('low', 0))),
                "close": float(row.get('Close', row.get('close', 0))),
                "volume": int(row.get('Volume', row.get('volume', 0)))
            })
        
        return market_data
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving market data: {str(e)}")
