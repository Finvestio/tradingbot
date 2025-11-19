from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.data.loader import load_market_data
import pandas as pd
import os, requests
from fastapi import Query
from dotenv import load_dotenv
import os
from threading import Thread
import time
import queue
import json
import threading
import asyncio
from app.bot.rl_trader import RLTrader
from fastapi import WebSocket, WebSocketDisconnect


# Import dependencies with proper error handling
from app.data.loader import load_market_data
from app.backtest.metrics import compute_equity_curve, compute_metrics
from app.database import get_db

# Import MySQL functions with fallback for when mysql-connector is not available
try:
    from app.db import (get_db_cursor, update_user_wallet, get_user_wallet, 
                       update_portfolio, record_order, get_user_portfolio, 
                       get_user_orders, init_database)
    MYSQL_AVAILABLE = True
    print("✅ MySQL connector available - database features enabled")
except ImportError:
    print("⚠️ MySQL connector not available - using fallback functions")
    MYSQL_AVAILABLE = False
    
    # Define fallback functions that return safe defaults
    def get_db_cursor(): return None, None
    def update_user_wallet(user_id, balance): return False
    def get_user_wallet(user_id): return 100000.0  # Default wallet balance
    def update_portfolio(user_id, symbol, asset_type, quantity, price, side): return False
    def record_order(user_id, symbol, asset_type, side, price, quantity): return False
    def get_user_portfolio(user_id): return []
    def get_user_orders(user_id, limit=50): return []
    def init_database(): return False

# Try to import orders router, but make it optional
try:
    from app.api_orders import router as orders_router
except ImportError:
    print("⚠️ Orders router not available - continuing without it")
    orders_router = None

# Try to import RL configuration router
try:
    from app.api_rl_config import router as rl_config_router
except ImportError:
    print("⚠️ RL Config router not available - continuing without it")
    rl_config_router = None

# Try to import RL explanation router
try:
    from app.api_rl_explanation import router as rl_explanation_router
except ImportError:
    print("⚠️ RL Explanation router not available - continuing without it")
    rl_explanation_router = None

app = FastAPI(title="Trading Bot API")

# Register the orders router if available
if orders_router:
    app.include_router(orders_router)
    print("✅ Orders router registered")
else:
    print("⚠️ Orders router not available - skipping registration")

# Register the RL configuration router if available
if rl_config_router:
    app.include_router(rl_config_router)
    print("✅ RL Configuration router registered")
else:
    print("⚠️ RL Configuration router not available - skipping registration")

# Register the RL explanation router if available
if rl_explanation_router:
    app.include_router(rl_explanation_router)
    print("✅ RL Explanation router registered")
else:
    print("⚠️ RL Explanation router not available - skipping registration")

# Global dictionary to track active trading bots
active_bots = {}

# Global dictionary to track notification queues for Server-Sent Events
notification_queues = {}

# Global dictionary to track pending trade proposals waiting for user approval
pending_proposals = {}

# Global dictionary to track WebSocket message queues
ws_message_queues = {}

# Global dictionary to track active WebSocket connections
active_connections = {}

# Initialize database tables on startup
init_database()

def send_notification(user_id: int, message: str, trade_data: dict = None):
    """
    Send real-time notification to user via Server-Sent Events and WebSocket
    """
    # Send via SSE (existing functionality)
    if user_id in notification_queues:
        try:
            notification_queues[user_id].put_nowait(message)
        except queue.Full:
            pass
    
    # Store WebSocket messages for later sending
    if trade_data:
        try:
            # Initialize WebSocket message queue if needed
            if user_id not in ws_message_queues:
                ws_message_queues[user_id] = queue.Queue(maxsize=100)
            
            ws_message_queues[user_id].put_nowait(trade_data)
            print(f"📨 Queued WebSocket message for user {user_id}: {trade_data.get('type', 'unknown')}")
        except queue.Full:
            print(f"⚠️ WebSocket message queue full for user {user_id}")
        except Exception as e:
            print(f"❌ Error queuing WebSocket message: {e}")

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
# Users endpoint for strategy analysis
# -------------------------------------------------------------
@app.get("/api/users")
def get_users(db: Session = Depends(get_db)):
    """
    Get available users with their wallet balances from database for strategy analysis
    """
    try:
        # Import User model here to avoid circular imports
        from .models import User
    except ImportError:
        from models import User
    
    try:
        users = db.query(User).all()
        return [
            {
                "id": user.id,
                "name": user.username,
                "wallet": user.wallet_balance,
                "email": user.email
            }
            for user in users
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching users: {str(e)}")

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
# Dynamic chart data endpoint
# -------------------------------------------------------------
@app.get("/api/chart_data")
def get_chart_data(symbol: str, asset_type: str = "stock", interval: str = "1day", outputsize: int = 100):
    """
    Fetch dynamic market data from TwelveData for the chosen asset type and symbol.
    Returns formatted data with SMA calculations for live charts.
    Always fetches fresh data from API to ensure real-time accuracy.
    """
    try:
        # Force fresh fetch from API instead of using stale cache
        from app.data.loader import fetch_from_api, save_to_db
        print(f"🔄 Fetching fresh chart data for {symbol} ({asset_type}) from API...")
        
        try:
            # Fetch fresh data from API
            df = fetch_from_api(symbol, asset_type, interval, outputsize)
            # Update cache with fresh data
            cache_key = f"{symbol}_{asset_type}" if asset_type != "stock" else symbol
            save_to_db(cache_key, df)
            print(f"✅ Fresh data fetched and cached: {len(df)} rows")
        except Exception as e:
            print(f"⚠️ Fresh fetch failed: {e}, trying cached data...")
            # Fallback to cached data if API fails
            df = load_market_data(symbol, asset_type, interval, outputsize)
        
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No market data found for {asset_type}:{symbol}")
        
        # Ensure we have Close column
        if "Close" not in df.columns:
            raise HTTPException(status_code=500, detail="Invalid data format: missing Close column")
        
        # Calculate SMAs
        df["SMA_fast"] = df["Close"].rolling(10).mean()
        df["SMA_slow"] = df["Close"].rolling(20).mean()
        
        # Get the last 'outputsize' records
        df = df.tail(outputsize)
        
        # Reset index to include Date as a column
        df_reset = df.reset_index()
        
        # Convert to records format, ensuring datetime is serializable
        records = []
        for _, row in df_reset.iterrows():
            # Handle Date column
            date_val = row.get("Date", None)
            if date_val is None or pd.isna(date_val):
                continue
                
            if hasattr(date_val, 'strftime'):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = str(date_val)
            
            # Handle Close price
            close_val = row.get("Close", None)
            if close_val is None or pd.isna(close_val):
                continue
            
            record = {
                "Date": date_str,
                "Close": float(close_val),
                "SMA_fast": float(row["SMA_fast"]) if not pd.isna(row.get("SMA_fast")) else None,
                "SMA_slow": float(row["SMA_slow"]) if not pd.isna(row.get("SMA_slow")) else None
            }
            records.append(record)
        
        if not records:
            raise HTTPException(status_code=404, detail=f"No valid data points found for {asset_type}:{symbol}")
        
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "data": records
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching chart data: {str(e)}")

# -------------------------------------------------------------
# Run trading strategy endpoint
# -------------------------------------------------------------
@app.post("/api/run_strategy")
def run_strategy(payload: dict):
    """
    Run trading simulation for a given symbol, asset type, and user.
    Example payload:
    {
        "symbol": "AAPL", 
        "asset_type": "stock", 
        "user_id": 1, 
        "fast": 10, 
        "slow": 20
    }
    """
    symbol = payload.get("symbol")
    asset_type = payload.get("asset_type", "stock")
    user_id = payload.get("user_id")
    fast = int(payload.get("fast", 10))
    slow = int(payload.get("slow", 20))

    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    # Log user activity
    print(f"Running strategy for user {user_id} on {asset_type}:{symbol}")

    # Load market data with asset type support - force fresh fetch
    try:
        # Force fresh fetch from API to ensure current data
        from app.data.loader import fetch_from_api, save_to_db
        try:
            df = fetch_from_api(symbol, asset_type, interval="1day", outputsize=5000)
            # Update cache
            cache_key = f"{symbol}_{asset_type}" if asset_type != "stock" else symbol
            save_to_db(cache_key, df)
            print(f"🔄 Fresh data fetched for strategy analysis: {len(df)} rows")
        except Exception as e:
            print(f"⚠️ Fresh fetch failed: {e}, using cached data")
            df = load_market_data(symbol, asset_type)
        
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No market data found for {asset_type}:{symbol}")
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
        "asset_type": asset_type,
        "user_id": user_id,
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

    # Load market data - force fresh fetch for signals
    try:
        from app.data.loader import fetch_from_api, save_to_db
        try:
            # Fetch fresh data for signals
            df = fetch_from_api(symbol, "stock", interval="1day", outputsize=5000)
            save_to_db(symbol, df)
            print(f"🔄 Fresh data fetched for signals: {len(df)} rows")
        except Exception as e:
            print(f"⚠️ Fresh fetch failed: {e}, using cached data")
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

@app.get("/api/realtime_price")
def get_realtime_price(symbol: str, asset_type: str = "stock"):
    """
    Get real-time price quote from Twelve Data API
    """
    try:
        from app.data.loader import fetch_realtime_price
        price_data = fetch_realtime_price(symbol, asset_type)
        return price_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching real-time price: {str(e)}")

@app.get("/api/market_data")
async def get_market_data(symbol: str, asset_type: str = "stock"):
    """
    Get cached market data for a symbol from MySQL database, or fetch from API if not cached
    """
    try:
        # Try to load from cache first
        df = load_market_data(symbol, asset_type)
        
        if df is None or df.empty:
            # If no cached data, fetch fresh from API
            print(f"⚠️ No cached data for {symbol}, fetching from API...")
            from app.data.loader import fetch_from_api
            df = fetch_from_api(symbol, asset_type, interval="1day", outputsize=100)
            # Save to cache
            from app.data.loader import save_to_db
            save_to_db(symbol, df)
        
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
            
            # Get values with fallbacks
            open_val = row.get('Open', row.get('open', row.get('Close', row.get('close', 0))))
            high_val = row.get('High', row.get('high', row.get('Close', row.get('close', 0))))
            low_val = row.get('Low', row.get('low', row.get('Close', row.get('close', 0))))
            close_val = row.get('Close', row.get('close', 0))
            volume_val = row.get('Volume', row.get('volume', 0))
            
            market_data.append({
                "symbol": symbol.upper(),
                "date": date_str,
                "open": float(open_val) if not pd.isna(open_val) else float(close_val),
                "high": float(high_val) if not pd.isna(high_val) else float(close_val),
                "low": float(low_val) if not pd.isna(low_val) else float(close_val),
                "close": float(close_val),
                "volume": int(volume_val) if not pd.isna(volume_val) else 0
            })
        
        return market_data
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving market data: {str(e)}")

# -------------------------------------------------------------
# Automated Trading Bot Endpoints (DEPRECATED - Use RL Bot below)
# -------------------------------------------------------------
# This old SMA bot endpoint is DISABLED - RL bot is used instead

@app.post("/api/start_bot_OLD_DISABLED")  # RENAMED - Old SMA bot (not used)
def start_bot_old_sma(payload: dict):
    """
    Start an automated trading bot for the specified user, asset type, and symbol.
    The bot runs SMA crossover strategy and executes trades every 30 seconds.
    
    Expected payload:
    {
        "symbol": "AAPL",
        "asset_type": "stock",
        "user_id": 1,
        "auto_execute": false  # If true, bot executes trades automatically without user approval
    }
    """
    symbol = payload.get("symbol")
    asset_type = payload.get("asset_type", "stock")
    user_id = payload.get("user_id")
    auto_execute = payload.get("auto_execute", False)  # Default to manual approval

    if not symbol or not user_id:
        raise HTTPException(status_code=400, detail="Symbol and user_id are required")

    # Check if bot is already running for this user
    if user_id in active_bots:
        return {"status": "already_running", "message": f"Bot already active for user {user_id}"}

    def bot_loop():
        """
        Main bot loop that runs SMA crossover strategy every 30 seconds
        Enhanced with MySQL database integration for real portfolio management
        Can execute trades automatically or wait for user approval based on auto_execute flag
        """
        try:
            # Get user's current wallet balance from database or use default
            wallet = get_user_wallet(user_id)
            if wallet is None and MYSQL_AVAILABLE:
                print(f"❌ Could not get wallet for user {user_id}")
                return
            elif not MYSQL_AVAILABLE:
                wallet = 100000.0  # Default wallet balance
                print(f"⚠️ Using default wallet balance: ${wallet:,.2f}")
            
            fast_period = 10
            slow_period = 20
            
            while user_id in active_bots:
                try:
                    # Fetch latest market data (force fresh fetch for real-time trading)
                    from app.data.loader import fetch_from_api, save_to_db
                    df = load_market_data(symbol, asset_type)
                    
                    # Force refresh: fetch fresh data from API to ensure we have latest prices
                    try:
                        fresh_df = fetch_from_api(symbol, asset_type, interval="1day", outputsize=100)
                        if not fresh_df.empty:
                            # Update cache with fresh data
                            cache_key = f"{symbol}_{asset_type}" if asset_type != "stock" else symbol
                            save_to_db(cache_key, fresh_df)
                            df = fresh_df
                            print(f"🔄 Refreshed market data from API for {symbol}")
                    except Exception as e:
                        print(f"⚠️ Failed to refresh data from API: {e}, using cached data")
                    
                    if df is None or df.empty:
                        print(f"❌ No market data available for {asset_type}:{symbol}")
                        time.sleep(30)
                        continue
                    
                    # Calculate SMAs
                    df["SMA_fast"] = df["Close"].rolling(fast_period).mean()
                    df["SMA_slow"] = df["Close"].rolling(slow_period).mean()
                    
                    # Get REAL-TIME price instead of last cached price
                    try:
                        from app.data.loader import fetch_realtime_price
                        realtime_data = fetch_realtime_price(symbol, asset_type)
                        current_price = float(realtime_data["price"])
                    except Exception as e:
                        latest = df.tail(1).iloc[0]
                        current_price = float(latest["Close"])
                    
                    # Get SMA values from latest data
                    latest = df.tail(1).iloc[0]
                    sma_fast = latest["SMA_fast"]
                    sma_slow = latest["SMA_slow"]
                    
                    # Skip if SMAs are not available (not enough data)
                    if pd.isna(sma_fast) or pd.isna(sma_slow):
                        time.sleep(30)
                        continue
                    
                    # Get current wallet balance from database
                    current_wallet = get_user_wallet(user_id)
                    if current_wallet is None:
                        print(f"❌ Cannot get current wallet for user {user_id}")
                        time.sleep(30)
                        continue
                    
                    wallet = current_wallet
                    
                    # SMA Crossover Trading Logic - Auto Execute or Create Proposals
                    if sma_fast > sma_slow and wallet >= current_price:
                        # BUY Signal - Fast SMA above Slow SMA
                        quantity_to_buy = 1
                        cost = quantity_to_buy * current_price
                        
                        if wallet >= cost:
                            if auto_execute:
                                # Auto-execute the trade immediately
                                from app.broker.portfolio import PortfolioManager
                                from app.database import get_db
                                db = next(get_db())
                                portfolio_mgr = PortfolioManager(db)
                                
                                try:
                                    result = portfolio_mgr.execute_trade(
                                        user_id=user_id,
                                        symbol=symbol,
                                        action="BUY",
                                        quantity=quantity_to_buy,
                                        price=current_price,
                                        asset_type=asset_type
                                    )
                                    
                                    print(f"🤖 AUTO-EXECUTED: BUY {quantity_to_buy} {symbol} @ ${current_price:.2f}")
                                    
                                    # Send execution notification
                                    send_notification(user_id, f"🤖 Auto-executed BUY {quantity_to_buy} {symbol} @ ${current_price:.2f}", {
                                        "type": "trade_executed",
                                        "action": "BUY",
                                        "symbol": symbol,
                                        "quantity": quantity_to_buy,
                                        "price": current_price,
                                        "result": result
                                    })
                                except Exception as e:
                                    print(f"❌ Auto-execution failed: {e}")
                            else:
                                # Create trade proposal for user approval
                                proposal_id = f"proposal_{user_id}_{int(time.time())}_{symbol}"
                                proposal = {
                                    "proposal_id": proposal_id,
                                    "user_id": user_id,
                                    "symbol": symbol,
                                    "asset_type": asset_type,
                                    "action": 1,  # BUY
                                    "price": current_price,
                                    "quantity": quantity_to_buy,
                                    "cost": cost,
                                    "equity": wallet,
                                    "timestamp": time.time(),
                                    "confidence": abs(sma_fast - sma_slow) / sma_slow  # Signal strength
                                }
                                
                                # Store proposal for user approval
                                pending_proposals[proposal_id] = proposal
                                
                                # Send proposal notification via WebSocket
                                proposal_message = f"🤖 Bot wants to BUY {quantity_to_buy} {symbol} @ ${current_price:.2f} - Your approval needed!"
                                send_notification(user_id, proposal_message, {
                                    "type": "trade_proposal",
                                    "proposal": proposal
                                })
                    
                    elif sma_fast < sma_slow:
                        # Check if user has position to sell
                        if MYSQL_AVAILABLE:
                            portfolio = get_user_portfolio(user_id)
                            user_position = None
                            for position in portfolio:
                                if position['symbol'] == symbol and position['asset_type'] == asset_type:
                                    user_position = position
                                    break
                            has_position = user_position and user_position['quantity'] > 0
                            quantity_available = user_position['quantity'] if user_position else 0
                        else:
                            # For simulation, assume we have 1 share to sell
                            has_position = True  # Simulate having position
                            quantity_available = 1
                        
                        if has_position:
                            # SELL Signal - Fast SMA below Slow SMA
                            quantity_to_sell = min(1, quantity_available)  # Sell 1 or remaining quantity
                            revenue = quantity_to_sell * current_price
                            
                            if auto_execute:
                                # Auto-execute the trade immediately
                                from app.broker.portfolio import PortfolioManager
                                from app.database import get_db
                                db = next(get_db())
                                portfolio_mgr = PortfolioManager(db)
                                
                                try:
                                    result = portfolio_mgr.execute_trade(
                                        user_id=user_id,
                                        symbol=symbol,
                                        action="SELL",
                                        quantity=quantity_to_sell,
                                        price=current_price,
                                        asset_type=asset_type
                                    )
                                    
                                    print(f"🤖 AUTO-EXECUTED: SELL {quantity_to_sell} {symbol} @ ${current_price:.2f}")
                                    
                                    # Send execution notification
                                    send_notification(user_id, f"🤖 Auto-executed SELL {quantity_to_sell} {symbol} @ ${current_price:.2f}", {
                                        "type": "trade_executed",
                                        "action": "SELL",
                                        "symbol": symbol,
                                        "quantity": quantity_to_sell,
                                        "price": current_price,
                                        "result": result
                                    })
                                except Exception as e:
                                    print(f"❌ Auto-execution failed: {e}")
                            else:
                                # Create SELL proposal for user approval
                                proposal_id = f"proposal_{user_id}_{int(time.time())}_{symbol}"
                                proposal = {
                                    "proposal_id": proposal_id,
                                    "user_id": user_id,
                                    "symbol": symbol,
                                    "asset_type": asset_type,
                                    "action": 2,  # SELL
                                    "price": current_price,
                                    "quantity": quantity_to_sell,
                                    "revenue": revenue,
                                    "equity": wallet,
                                    "timestamp": time.time(),
                                    "confidence": abs(sma_slow - sma_fast) / sma_fast  # Signal strength
                                }
                                
                                # Store proposal for user approval
                                pending_proposals[proposal_id] = proposal
                                
                                # Send proposal notification via WebSocket
                                proposal_message = f"🤖 Bot wants to SELL {quantity_to_sell} {symbol} @ ${current_price:.2f} - Your approval needed!"
                                send_notification(user_id, proposal_message, {
                                    "type": "trade_proposal",
                                    "proposal": proposal
                                })
                        else:
                            # HOLD - No position to sell
                            print(f"⚪ HOLD {symbol} - No position to sell")
                    
                    else:
                        # HOLD - No clear signal or insufficient funds
                        print(f"⚪ HOLD {symbol} at ${current_price:.2f} | Wallet: ${wallet:,.2f}")
                        print(f"   📊 Fast SMA: ${sma_fast:.2f} | Slow SMA: ${sma_slow:.2f}")
                    
                except Exception as e:
                    print(f"❌ Bot error for user {user_id}: {str(e)}")
                
                # Wait 30 seconds before next trade cycle
                time.sleep(30)
                
        except Exception as e:
            print(f"❌ Critical bot error for user {user_id}: {str(e)}")
        finally:
            # Clean up when bot stops
            if user_id in active_bots:
                del active_bots[user_id]
            print(f"🛑 Bot stopped for user {user_id}")

    # Start bot in background thread
    bot_thread = Thread(target=bot_loop, daemon=True)
    bot_thread.start()
    active_bots[user_id] = bot_thread
    
    return {
        "status": "bot_started",
        "symbol": symbol,
        "asset_type": asset_type,
        "user_id": user_id,
        "message": f"Automated trading bot started for user {user_id} on {asset_type}:{symbol}"
    }

@app.post("/api/stop_bot_OLD_DISABLED")
def stop_bot_old(payload: dict):
    """
    OLD ENDPOINT - DISABLED
    Stop the automated trading bot for the specified user.
    
    Expected payload:
    {
        "user_id": 1
    }
    """
    user_id = payload.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    if user_id in active_bots:
        # Remove from active bots (this will cause the bot loop to exit)
        del active_bots[user_id]
        return {
            "status": "bot_stopped",
            "user_id": user_id,
            "message": f"Trading bot stopped for user {user_id}"
        }
    else:
        return {
            "status": "not_running",
            "user_id": user_id,
            "message": f"No active bot found for user {user_id}"
        }

@app.get("/api/bot_status/{user_id}")
def get_bot_status(user_id: int):
    """
    Check if a trading bot is currently running for the specified user.
    """
    is_running = user_id in active_bots
    return {
        "user_id": user_id,
        "is_running": is_running,
        "status": "running" if is_running else "stopped"
    }

# -------------------------------------------------------------
# Server-Sent Events for Real-time Notifications
# -------------------------------------------------------------

@app.get("/api/notifications/{user_id}")
def stream_notifications(user_id: int):
    """
    Server-Sent Events endpoint for real-time trade notifications
    """
    def event_stream():
        # Create a queue for this user
        q = queue.Queue(maxsize=100)
        notification_queues[user_id] = q
        
        try:
            # Send initial connection message
            yield f"data: Connected to notifications for user {user_id}\n\n"
            
            while True:
                try:
                    # Wait for notification with timeout
                    message = q.get(timeout=30)  # 30 second timeout
                    yield f"data: {message}\n\n"
                except queue.Empty:
                    # Send keepalive message
                    yield f"data: keepalive\n\n"
                except Exception as e:
                    print(f"❌ SSE error for user {user_id}: {e}")
                    break
        
        except Exception as e:
            print(f"❌ SSE stream error for user {user_id}: {e}")
        
        finally:
            # Clean up queue when client disconnects
            if user_id in notification_queues:
                del notification_queues[user_id]
                print(f"🧹 Notification queue cleaned up for user {user_id}")
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

# -------------------------------------------------------------
# Portfolio and Wallet Management Endpoints
# -------------------------------------------------------------

@app.get("/api/wallet/{user_id}")
def get_wallet_balance(user_id: int):
    """
    Get user's current wallet balance from MySQL database
    """
    wallet = get_user_wallet(user_id)
    if wallet is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found or wallet inaccessible")
    
    return {
        "user_id": user_id,
        "wallet_balance": wallet,
        "currency": "USD"
    }

@app.get("/api/portfolio/{user_id}")
def get_portfolio_holdings(user_id: int):
    """
    Get user's current portfolio holdings from MySQL database
    """
    try:
        portfolio = get_user_portfolio(user_id)
        
        # Calculate totals
        total_value = sum(float(position['total_value']) for position in portfolio)
        
        return {
            "user_id": user_id,
            "holdings": portfolio,
            "total_holdings_value": total_value,
            "positions_count": len(portfolio)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching portfolio: {str(e)}")

@app.get("/api/orders/{user_id}")
def get_order_history(user_id: int, limit: int = 50):
    """
    Get user's recent order history from MySQL database
    """
    try:
        orders = get_user_orders(user_id, limit)
        
        return {
            "user_id": user_id,
            "orders": orders,
            "total_orders": len(orders)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching orders: {str(e)}")

@app.get("/api/portfolio_summary/{user_id}")
def get_portfolio_summary(user_id: int):
    """
    Get comprehensive portfolio summary including wallet, holdings, and recent trades
    Uses REAL-TIME prices for accurate portfolio valuation
    """
    try:
        # Get wallet balance
        wallet = get_user_wallet(user_id)
        if wallet is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        # Get portfolio holdings
        portfolio = get_user_portfolio(user_id)
        
        # Update each holding with real-time prices from Twelve Data API
        from app.data.loader import fetch_realtime_price
        updated_holdings = []
        total_holdings_value = 0.0
        
        print(f"📊 Fetching real-time prices for {len(portfolio)} holdings...")
        
        for position in portfolio:
            symbol = position.get('symbol', '')
            asset_type = position.get('asset_type', 'stock')
            quantity = float(position.get('quantity', 0))
            avg_price = float(position.get('avg_price', 0))
            
            if not symbol or quantity <= 0:
                continue
            
            # Fetch REAL-TIME price from Twelve Data API
            current_price = avg_price  # Default fallback
            price_fetched = False
            
            try:
                realtime_data = fetch_realtime_price(symbol, asset_type)
                current_price = float(realtime_data["price"])
                price_fetched = True
                print(f"✅ Real-time price for {symbol}: ${current_price:.2f} (was avg: ${avg_price:.2f})")
            except Exception as e:
                # Fallback to avg_price if real-time fetch fails, but log the error
                print(f"⚠️ Failed to fetch real-time price for {symbol} ({asset_type}): {e}")
                print(f"   Using avg_price ${avg_price:.2f} as fallback")
                current_price = avg_price
                price_fetched = False
            
            # Calculate real-time values using current_price
            total_value = quantity * current_price
            unrealized_pnl = (current_price - avg_price) * quantity
            
            updated_holdings.append({
                "symbol": symbol,
                "asset_type": asset_type,
                "quantity": quantity,
                "avg_price": avg_price,
                "current_price": current_price,
                "total_value": total_value,
                "unrealized_pnl": unrealized_pnl,
                "price_is_realtime": price_fetched  # Flag to indicate if price is real-time
            })
            
            total_holdings_value += total_value
        
        print(f"📊 Portfolio updated: {len(updated_holdings)} holdings, total value: ${total_holdings_value:.2f}")
        
        # Get recent orders (manual orders)
        recent_orders = get_user_orders(user_id, 10)
        
        # Get recent bot trades from bot_trades table
        try:
            from app.db import get_db_cursor
            with get_db_cursor() as (cur, cnx):
                if cur:
                    cur.execute("""
                        SELECT id, symbol, asset_type, action, price, quantity, reward, equity, timestamp
                        FROM bot_trades
                        WHERE user_id = %s
                        ORDER BY timestamp DESC
                        LIMIT 10
                    """, (user_id,))
                    bot_trades = cur.fetchall()
                    
                    # Format bot trades to match recent_orders format
                    formatted_bot_trades = []
                    for trade in bot_trades:
                        formatted_bot_trades.append({
                            "id": trade["id"],
                            "symbol": trade["symbol"],
                            "asset_type": trade["asset_type"],
                            "side": trade["action"],  # BUY, SELL, or HOLD
                            "price": float(trade["price"]),
                            "quantity": float(trade["quantity"]),
                            "reward": float(trade.get("reward", 0)),
                            "equity": float(trade.get("equity", 0)),
                            "timestamp": trade["timestamp"].isoformat() if trade["timestamp"] else None,
                            "source": "bot"  # Mark as bot trade
                        })
                    
                    # Combine manual orders and bot trades, sort by timestamp
                    all_recent = recent_orders + formatted_bot_trades
                    # Sort by timestamp descending (most recent first)
                    all_recent.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
                    recent_orders = all_recent[:10]  # Limit to 10 most recent
        except Exception as e:
            print(f"⚠️ Error loading bot trades: {e}")
            # Continue with just manual orders if bot trades fail
        
        return {
            "user_id": user_id,
            "wallet_balance": wallet,
            "total_holdings_value": total_holdings_value,
            "total_portfolio_value": wallet + total_holdings_value,
            "holdings": updated_holdings,
            "recent_orders": recent_orders,
            "positions_count": len(updated_holdings)
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching portfolio summary: {str(e)}")

@app.get("/api/bot_trades/{user_id}")
def get_bot_trades(user_id: int, limit: int = 50):
    """
    Get bot trading history with rewards for a specific user.
    Returns trades sorted by most recent first.
    """
    try:
        with get_db_cursor() as (cur, cnx):
            if cur is None:
                return {"user_id": user_id, "total_trades": 0, "trades": []}
            
            cur.execute("""
                SELECT id, symbol, asset_type, action, price, quantity, reward, equity, timestamp
                FROM bot_trades
                WHERE user_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (user_id, limit))
            
            trades = cur.fetchall()
        
        # Format trades for frontend
        formatted_trades = []
        for trade in trades:
            formatted_trades.append({
                "id": trade["id"],
                "symbol": trade["symbol"],
                "asset_type": trade["asset_type"],
                "action": trade["action"],
                "price": float(trade["price"]),
                "quantity": float(trade["quantity"]),
                "reward": float(trade["reward"]),
                "equity": float(trade["equity"]),
                "timestamp": trade["timestamp"].isoformat() if trade["timestamp"] else None
            })
        
        return {
            "user_id": user_id,
            "total_trades": len(formatted_trades),
            "trades": formatted_trades
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching bot trades: {str(e)}")

running_bots = {}

@app.post("/api/start_bot")
def start_bot(payload: dict):
    """
    Start the RL trading bot for a user and asset(s).
    Supports both single-asset and multi-asset portfolio trading.
    
    Single-asset example:
    {
        "user_id": 1,
        "symbol": "AAPL",
        "asset_type": "stock",
        "interval_sec": 30,
        "auto_execute": true
    }
    
    Multi-asset portfolio example:
    {
        "user_id": 1,
        "symbols": [["AAPL", "stock"], ["BTC/USD", "crypto"], ["TSLA", "stock"]],
        "interval_sec": 30,
        "auto_execute": true,
        "use_per": true
    }
    """
    user_id = payload.get("user_id")
    symbol = payload.get("symbol")
    asset_type = payload.get("asset_type", "stock")
    symbols = payload.get("symbols")  # Multi-asset: list of [symbol, asset_type] pairs
    interval_sec = int(payload.get("interval_sec", 30))  # Default 30 seconds
    auto_execute = payload.get("auto_execute", True)  # Default to auto-execute
    use_per = payload.get("use_per", True)  # Default to using Prioritized Experience Replay

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    # Determine if multi-asset or single-asset
    if symbols and isinstance(symbols, list) and len(symbols) > 1:
        # Multi-asset portfolio mode
        if not all(isinstance(s, (list, tuple)) and len(s) == 2 for s in symbols):
            raise HTTPException(status_code=400, detail="symbols must be list of [symbol, asset_type] pairs")
        
        symbols_tuples = [(str(s[0]), str(s[1])) for s in symbols]
        key = f"{user_id}_portfolio_{len(symbols_tuples)}assets"
        
        print(f"\n{'='*80}")
        print(f"🚀 STARTING MULTI-ASSET PORTFOLIO RL BOT")
        print(f"{'='*80}")
        print(f"User ID: {user_id}")
        print(f"Assets: {', '.join([f'{s[0]} ({s[1]})' for s in symbols_tuples])}")
        print(f"Number of Assets: {len(symbols_tuples)}")
        print(f"Interval: {interval_sec} seconds")
        print(f"Auto Execute: {auto_execute}")
        print(f"Prioritized Experience Replay: {use_per}")
        print(f"{'='*80}\n")
    else:
        # Single-asset mode (backward compatible)
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required (or provide symbols for multi-asset)")
        
        key = f"{user_id}_{symbol}_{asset_type}"
        symbols_tuples = None
        
        print(f"\n{'='*80}")
        print(f"🚀 STARTING RL BOT")
        print(f"{'='*80}")
        print(f"User ID: {user_id}")
        print(f"Symbol: {symbol}")
        print(f"Asset Type: {asset_type}")
        print(f"Interval: {interval_sec} seconds")
        print(f"Auto Execute: {auto_execute}")
        print(f"Prioritized Experience Replay: {use_per}")
        print(f"{'='*80}\n")
    
    if key in running_bots:
        raise HTTPException(status_code=400, detail="Bot already running for this user/asset(s)")

    def run_bot_with_error_handling():
        try:
            bot.run()
        except Exception as e:
            print(f"\n{'!'*80}")
            print(f"❌ CRITICAL BOT ERROR - Thread crashed!")
            print(f"{'!'*80}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            print(f"{'!'*80}\n")

    # Create bot with appropriate parameters
    if symbols_tuples:
        # Multi-asset portfolio mode
        bot = RLTrader(user_id, symbol=None, asset_type=None, interval_sec=interval_sec, 
                      auto_execute=auto_execute, symbols=symbols_tuples, use_per=use_per)
    else:
        # Single-asset mode
        bot = RLTrader(user_id, symbol, asset_type, interval_sec, auto_execute, 
                      symbols=None, use_per=use_per)
    
    thread = threading.Thread(target=run_bot_with_error_handling, daemon=True)
    thread.start()
    running_bots[key] = bot

    if symbols_tuples:
        print(f"✅ Multi-asset portfolio bot thread started successfully for {len(symbols_tuples)} assets")
        return {
            "status": "started",
            "mode": "multi_asset",
            "num_assets": len(symbols_tuples),
            "symbols": [{"symbol": s[0], "asset_type": s[1]} for s in symbols_tuples],
            "use_per": use_per
        }
    else:
        print(f"✅ Bot thread started successfully for {symbol}")
        return {
            "status": "started",
            "mode": "single_asset",
            "symbol": symbol, 
            "asset_type": asset_type, 
            "user_id": user_id,
            "interval_sec": interval_sec,
            "auto_execute": auto_execute,
            "use_per": use_per
    }


@app.post("/api/stop_bot")
def stop_bot(payload: dict):
    """
    Stop a running bot by user and symbol.
    Example: {"user_id": 1, "symbol": "AAPL", "asset_type": "stock"}
    """
    user_id = payload.get("user_id")
    symbol = payload.get("symbol")
    asset_type = payload.get("asset_type", "stock")

    key = f"{user_id}_{symbol}_{asset_type}"
    bot = running_bots.get(key)
    if not bot:
        raise HTTPException(status_code=404, detail="No bot running for this user/asset")

    # Stop the bot by setting running flag to False
    bot.running = False
    running_bots.pop(key, None)
    
    print(f"🛑 Bot stopped for {symbol} ({asset_type}) — user {user_id}", flush=True)
    return {"status": "stopped", "symbol": symbol, "message": "Bot stopped successfully"}

@app.post("/api/trade_response")
def trade_response(payload: dict):
    """
    Handle user response to trade proposal (accept or reject).
    Expected payload: {user_id, symbol, decision: "accept"|"reject"}
    """
    from app.bot.rl_trader import trade_proposals
    
    user_id = payload.get("user_id")
    symbol = payload.get("symbol")
    decision = payload.get("decision")
    
    if not user_id or not symbol or not decision:
        raise HTTPException(status_code=400, detail="user_id, symbol, and decision are required")
    
    if decision not in ["accept", "reject"]:
        raise HTTPException(status_code=400, detail="decision must be 'accept' or 'reject'")
    
    # Get asset_type from payload or try to find proposal with/without asset_type
    asset_type = payload.get("asset_type", "stock")
    
    # Try to find proposal with asset_type first (new format)
    key = (user_id, symbol, asset_type)
    if key not in trade_proposals:
        # Try old format for backward compatibility
        key_old = (user_id, symbol)
        if key_old in trade_proposals:
            key = key_old
            print(f"⚠️ Found proposal with old key format (without asset_type), using it")
        else:
            raise HTTPException(status_code=404, detail=f"No pending trade proposal found for {symbol} ({asset_type})")
    
    proposal = trade_proposals[key]
    
    if decision == "accept":
        # Execute the trade
        try:
            # Find the running bot instance for this user/symbol
            key = f"{user_id}_{symbol}_{proposal.get('asset_type', 'stock')}"
            bot = running_bots.get(key)
            
            if bot:
                # Use the existing bot instance to execute the trade
                success = bot.execute_approved_trade(proposal)
            else:
                # Fallback: execute directly using PortfolioManager
                from app.broker.portfolio import PortfolioManager
                from app.database import get_db
                db = next(get_db())
                portfolio_mgr = PortfolioManager(db)
                
                action_str = {1: "BUY", 2: "SELL", 0: "HOLD"}.get(proposal["action"], "HOLD")
                if action_str in ["BUY", "SELL"]:
                    result = portfolio_mgr.execute_trade(
                        user_id=user_id,
                        symbol=symbol,
                        action=action_str,
                        quantity=proposal.get("quantity", 1),
                        price=proposal["price"],
                        asset_type=proposal.get("asset_type", "stock")
                    )
                    success = result.get("success", False)
                else:
                    success = False
            
            if success:
                # Remove proposal after successful execution
                del trade_proposals[key]
                print(f"✅ Trade approved and executed for user {user_id}: {proposal['action']} {symbol}")
                return {"status": "executed", "message": "Trade executed successfully"}
            else:
                return {"status": "error", "message": "Failed to execute trade"}
                
        except Exception as e:
            print(f"❌ Error executing approved trade: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Failed to execute trade: {str(e)}")
    
    else:  # decision == "reject"
        # Remove proposal and log rejection - NO EXECUTION HAPPENS
        del trade_proposals[key]
        action_name = {1: "BUY", 2: "SELL", 0: "HOLD"}.get(proposal["action"], "UNKNOWN")
        print(f"❌ TRADE REJECTED → User {user_id} rejected {action_name} {symbol} @ ${proposal.get('price', 0):.2f}")
        print(f"❌ No trade execution - proposal discarded")
        
        # Send rejection notification
        rejection_msg = {
            "type": "rejected",
            "user_id": user_id,
            "symbol": symbol,
            "action": proposal["action"],
            "timestamp": time.time()
        }
        
        # Send via existing notification system
        send_notification(user_id, f"Trade rejected: {action_name} {symbol}", rejection_msg)
        
        return {"status": "rejected", "message": f"{action_name} proposal rejected - no execution"}

@app.post("/api/test_proposal")
def test_proposal(payload: dict):
    """Create a test trade proposal for debugging with REAL-TIME prices from Twelve Data API."""
    user_id = payload.get("user_id", 1)
    symbol = payload.get("symbol", "AAPL")
    asset_type = payload.get("asset_type", "stock")
    
    # ✅ FETCH REAL-TIME PRICE FROM TWELVE DATA API
    try:
        from app.data.loader import fetch_realtime_price
        from app.db import get_user_wallet
        
        realtime_data = fetch_realtime_price(symbol, asset_type)
        current_price = float(realtime_data["price"])
        
        # Get user's current equity/wallet
        wallet = get_user_wallet(user_id)
        current_equity = wallet if wallet is not None else 10000.00
        
        print(f"📡 Test proposal: Fetched real-time price ${current_price:.2f} for {symbol} from Twelve Data API")
    except Exception as e:
        print(f"⚠️ Failed to fetch real-time price for test proposal: {e}")
        # Fallback to a default price (but log the error)
        current_price = 150.00
        current_equity = 10000.00
        print(f"⚠️ Using fallback price ${current_price:.2f} (API fetch failed)")
    
    # Create test proposal with REAL-TIME price
    proposal = {
        "type": "proposal",
        "user_id": user_id,
        "symbol": symbol,
        "asset_type": asset_type,
        "action": 1,  # BUY
        "price": current_price,  # ✅ REAL-TIME PRICE FROM API
        "equity": current_equity,
        "timestamp": time.time()
    }
    
    # Debug active connections
    print(f"🧪 Test proposal for user {user_id}")
    print(f"🧪 Active WebSocket connections: {list(active_connections.keys())}")
    
    # Send via WebSocket if connected
    ws = active_connections.get(user_id)
    if ws:
        try:
            import asyncio
            proposal_json = json.dumps(proposal)
            
            # Try to send the message
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(ws.send_text(proposal_json))
            loop.close()
            
            print(f"✅ Test proposal sent successfully to user {user_id}")
            return {"status": "sent", "proposal": proposal, "message": "Test proposal sent via WebSocket"}
            
        except Exception as e:
            error_msg = f"Failed to send test proposal: {str(e)}"
            print(f"❌ {error_msg}")
            return {"status": "error", "message": error_msg}
    else:
        error_msg = f"User {user_id} not connected via WebSocket. Active connections: {list(active_connections.keys())}"
        print(f"❌ {error_msg}")
        return {"status": "error", "message": error_msg}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    # Validate user_id before accepting connection
    if user_id is None or user_id == "undefined" or user_id == "":
        print(f"❌ Invalid user_id for WebSocket connection: {user_id}")
        await websocket.close(code=4003, reason="Invalid user_id")
        return
    
    # Convert to int
    try:
        user_id_int = int(user_id)
        if user_id_int <= 0:
            raise ValueError("User ID must be positive")
    except (ValueError, TypeError) as e:
        print(f"❌ Cannot convert user_id to int: {user_id} - {e}")
        await websocket.close(code=4003, reason="Invalid user_id format")
        return
    
    user_id = user_id_int  # Use the validated integer
    
    await websocket.accept()
    active_connections[user_id] = websocket
    print(f"✅ WebSocket connected for user {user_id}")
    
    # Initialize message queue for this user if not exists
    if user_id not in ws_message_queues:
        ws_message_queues[user_id] = queue.Queue(maxsize=100)
        print(f"📦 Created message queue for user {user_id}")
    else:
        pending_count = ws_message_queues[user_id].qsize()
        print(f"📦 Using existing message queue for user {user_id} (has {pending_count} pending messages)")
    
    # Send any pending messages that were queued before connection
    pending_sent = 0
    while user_id in ws_message_queues and not ws_message_queues[user_id].empty():
        try:
            message = ws_message_queues[user_id].get_nowait()
            await websocket.send_text(json.dumps(message))
            pending_sent += 1
            print(f"📤 Sent pending WebSocket message to user {user_id}: {message.get('type', 'unknown')}")
        except queue.Empty:
            break
        except Exception as e:
            print(f"❌ Error sending pending WebSocket message: {e}")
            break
    
    if pending_sent > 0:
        print(f"✅ Sent {pending_sent} pending messages to user {user_id} on connection")
    
    try:
        while True:
            # Actively check for queued messages to send (higher priority)
            messages_sent = 0
            while user_id in ws_message_queues and not ws_message_queues[user_id].empty():
                try:
                    message = ws_message_queues[user_id].get_nowait()
                    await websocket.send_text(json.dumps(message))
                    messages_sent += 1
                    print(f"📤 Sent queued WebSocket message to user {user_id}: {message.get('type', 'unknown')} - {message.get('symbol', 'N/A')}")
                except queue.Empty:
                    break
                except Exception as e:
                    print(f"❌ Error sending queued WebSocket message: {e}")
                    import traceback
                    traceback.print_exc()
                    break
            
            if messages_sent > 0:
                print(f"✅ Sent {messages_sent} queued message(s) to user {user_id}")
            
            # Small delay to prevent busy waiting
            await asyncio.sleep(0.05)  # Reduced from 0.1 to check more frequently
            
            # Try to receive (non-blocking) to detect disconnections
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                # Handle any incoming messages if needed
                print(f"📥 Received message from user {user_id}: {data}")
            except asyncio.TimeoutError:
                pass  # No message received, continue loop
                
    except WebSocketDisconnect:
        if user_id in active_connections:
            del active_connections[user_id]
        # Keep message queue for potential reconnection (messages will be sent when reconnected)
        print(f"❌ User {user_id} disconnected from WebSocket (queue preserved for reconnection)")
    except Exception as e:
        print(f"❌ WebSocket error for user {user_id}: {e}")
        if user_id in active_connections:
            del active_connections[user_id]

@app.post("/api/accept_trade")
def accept_trade(payload: dict):
    """
    Accept a trade proposal and execute the order via RL bot
    """
    proposal_id = payload.get("proposal_id")
    user_id = payload.get("user_id")
    
    if not proposal_id or not user_id:
        raise HTTPException(status_code=400, detail="proposal_id and user_id are required")
    
    print(f"✅ Accept trade request: proposal_id={proposal_id}, user_id={user_id}")
    
    # Try to find proposal in RL bot's trade_proposals (new system)
    from app.bot.rl_trader import trade_proposals
    import time
    
    # Get asset_type from payload if provided
    asset_type_from_payload = payload.get("asset_type", None)
    symbol_from_payload = payload.get("symbol", None)
    
    # Extract symbol from proposal_id (format: "user_id_symbol_timestamp")
    proposal_found = None
    proposal_key = None
    
    # Search in trade_proposals dictionary
    for key, prop in trade_proposals.items():
        # Check if proposal matches by ID or user_id
        if prop.get("proposal_id") == proposal_id or (prop.get("user_id") == user_id and (not symbol_from_payload or prop.get("symbol") == symbol_from_payload)):
            # If asset_type is provided, also match it
            if asset_type_from_payload:
                prop_asset_type = prop.get("asset_type", "stock")
                if prop_asset_type != asset_type_from_payload:
                    continue  # Skip if asset_type doesn't match
            
            # Check if this is the right proposal
            if prop.get("proposal_id") == proposal_id:
                proposal_found = prop
                proposal_key = key
                break
    
    if not proposal_found:
        # Fallback to old pending_proposals system
        if proposal_id in pending_proposals:
            proposal_found = pending_proposals[proposal_id]
            print(f"📋 Found proposal in old pending_proposals")
        else:
            print(f"❌ Proposal not found: {proposal_id}")
            print(f"📋 Available proposals: {list(trade_proposals.keys())}")
            raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found or already processed")
    
    proposal = proposal_found
    symbol = proposal.get("symbol")
    user_id_int = int(user_id) if isinstance(user_id, str) else user_id
    
    print(f"📋 Found proposal: {symbol} for user {user_id_int}")
    
    try:
        # Find the running RL bot for this user and symbol
        # Bot key format is: "{user_id}_{symbol}_{asset_type}"
        asset_type = proposal.get("asset_type", "stock")
        bot_key = f"{user_id_int}_{symbol}_{asset_type}"
        
        bot = running_bots.get(bot_key)
        
        print(f"🔍 Looking for bot with key: {bot_key}")
        print(f"🔍 Available bot keys: {list(running_bots.keys())}")
        
        if bot:
            print(f"🤖 Found running bot for {symbol}, executing approved trade...")
            print(f"📋 Proposal details: action={proposal.get('action')}, price=${proposal.get('price', 0):.2f}, symbol={symbol}")
            
            # Use RL bot's execute_approved_trade method (handles database recording)
            try:
                success = bot.execute_approved_trade(proposal)
                print(f"📊 Execute approved trade returned: {success}")
            except Exception as e:
                print(f"❌ Error in execute_approved_trade: {e}")
                import traceback
                traceback.print_exc()
                success = False
            
            if success:
                # Remove from trade_proposals
                if proposal_key and proposal_key in trade_proposals:
                    del trade_proposals[proposal_key]
                elif proposal_id in pending_proposals:
                    del pending_proposals[proposal_id]
                
                action_name = proposal.get("action_name", "BUY" if proposal["action"] == 1 else "SELL" if proposal["action"] == 2 else "HOLD")
                print(f"✅ Trade executed successfully: {action_name} {symbol}")
                return {
                    "status": "executed", 
                    "message": f"{action_name} order executed successfully",
                    "symbol": symbol,
                    "action": proposal["action"]
                }
            else:
                raise HTTPException(status_code=500, detail="Trade execution failed in bot")
        else:
            # Fallback: Use PortfolioManager if bot not found
            print(f"⚠️ Bot not found, using PortfolioManager fallback...")
            from app.broker.portfolio import PortfolioManager
            from app.db import get_db
            db = next(get_db())
            portfolio_mgr = PortfolioManager(db)
            
            action_str = "BUY" if proposal["action"] == 1 else "SELL" if proposal["action"] == 2 else "HOLD"
            
            if action_str in ["BUY", "SELL"]:
                result = portfolio_mgr.execute_trade(
                    user_id=user_id_int,
                    symbol=symbol,
                    action=action_str,
                    quantity=proposal.get("quantity", 1),
                    price=proposal["price"],
                    asset_type=proposal.get("asset_type", "stock")
                )
                
                # Remove from proposals
                if proposal_key and proposal_key in trade_proposals:
                    del trade_proposals[proposal_key]
                elif proposal_id in pending_proposals:
                    del pending_proposals[proposal_id]
                
                return {"status": "executed", "message": f"{action_str} order executed successfully", "result": result}
            else:
                return {"status": "ignored", "message": "HOLD action - no trade executed"}
            
    except Exception as e:
        print(f"❌ Trade execution error: {e}")
        import traceback
        traceback.print_exc()
        # Remove from proposals on error
        if proposal_key and proposal_key in trade_proposals:
            del trade_proposals[proposal_key]
        elif proposal_id in pending_proposals:
            del pending_proposals[proposal_id]
        raise HTTPException(status_code=500, detail=f"Trade execution failed: {str(e)}")

@app.post("/api/reject_trade")
def reject_trade(payload: dict):
    """
    Reject a trade proposal
    """
    proposal_id = payload.get("proposal_id")
    user_id = payload.get("user_id")
    
    if not proposal_id or not user_id:
        raise HTTPException(status_code=400, detail="proposal_id and user_id are required")
    
    print(f"❌ Reject trade request: proposal_id={proposal_id}, user_id={user_id}")
    
    # Try to find proposal in RL bot's trade_proposals (new system)
    from app.bot.rl_trader import trade_proposals
    
    proposal_found = None
    proposal_key = None
    
    # Search in trade_proposals dictionary
    for key, prop in trade_proposals.items():
        if prop.get("proposal_id") == proposal_id or prop.get("user_id") == user_id:
            if prop.get("proposal_id") == proposal_id:
                proposal_found = prop
                proposal_key = key
                break
    
    if not proposal_found:
        # Fallback to old pending_proposals system
        if proposal_id in pending_proposals:
            proposal_found = pending_proposals[proposal_id]
        else:
            print(f"❌ Proposal not found: {proposal_id}")
            raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found or already processed")
    
    proposal = proposal_found
    action_str = "BUY" if proposal["action"] == 1 else "SELL" if proposal["action"] == 2 else "HOLD"
    
    # Remove from proposals
    if proposal_key and proposal_key in trade_proposals:
        del trade_proposals[proposal_key]
        print(f"✅ Removed proposal from trade_proposals: {proposal_key}")
    elif proposal_id in pending_proposals:
        del pending_proposals[proposal_id]
        print(f"✅ Removed proposal from pending_proposals: {proposal_id}")
    
    # Send rejection notification
    send_notification(user_id, {
        "type": "trade_rejected",
        "message": f"❌ {action_str} proposal for {proposal['symbol']} rejected",
        "proposal": proposal
    })
    
    return {"status": "rejected", "message": "Trade proposal rejected successfully"}