from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

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
@app.get("/")
def root():
    return {"message": "Trading Bot API is running."}

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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ---------------------------------------------------------
    # Simple SMA crossover strategy
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
    # Prepare the last 10 equity points for the frontend table
    # ---------------------------------------------------------
    equity_df = equity_curve.tail(10).reset_index()
    equity_df.columns = ["Date", "Equity"]
    equity_df["Equity"] = equity_df["Equity"].astype(float)

    result = {
        "symbol": symbol,
        "metrics": metrics,
        "equity": equity_df.to_dict(orient="records"),
    }

    return result


# -------------------------------------------------------------
# Get trading signals endpoint
# -------------------------------------------------------------
@app.get("/api/signals")
def get_signals(symbol: str, fast: int = 10, slow: int = 20):
    """
    Get trading signals for a given symbol and SMA parameters.
    Returns the last 20 rows with Date, Close, SMA_fast, SMA_slow, and Signal.
    
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ---------------------------------------------------------
    # Compute SMAs and signals
    # ---------------------------------------------------------
    df["SMA_fast"] = df["Close"].rolling(fast).mean()
    df["SMA_slow"] = df["Close"].rolling(slow).mean()
    
    # Create Signal column
    df["Signal"] = 0
    df.loc[df["SMA_fast"] > df["SMA_slow"], "Signal"] = 1
    df.loc[df["SMA_fast"] < df["SMA_slow"], "Signal"] = -1

    # ---------------------------------------------------------
    # Prepare the last 20 rows with required columns
    # ---------------------------------------------------------
    # Get the last 20 rows, reset index, and format properly
    result_df = df[["Close", "SMA_fast", "SMA_slow", "Signal"]].tail(20).reset_index()
    
    # Ensure proper column naming (Date should be the first column after reset_index)
    result_df.columns = ["Date", "Close", "SMA_fast", "SMA_slow", "Signal"]
    
    # Format the Date column as string
    result_df["Date"] = result_df["Date"].dt.strftime("%Y-%m-%d")
    
    # Convert to dictionary format
    result = {
        "symbol": symbol,
        "fast": fast,
        "slow": slow,
        "signals": result_df.to_dict(orient="records")
    }

    return result

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
