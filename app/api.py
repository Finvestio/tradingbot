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

app = FastAPI(title="Trading Bot API")

# Register the orders router if available
if orders_router:
    app.include_router(orders_router)
    print("✅ Orders router registered")
else:
    print("⚠️ Orders router not available - skipping registration")

# Global dictionary to track active trading bots
active_bots = {}

# Global dictionary to track notification queues for Server-Sent Events
notification_queues = {}

# Initialize database tables on startup
init_database()

def send_notification(user_id: int, message: str):
    """
    Send real-time notification to user via Server-Sent Events
    """
    if user_id in notification_queues:
        try:
            notification_queues[user_id].put_nowait(message)
            print(f"📡 Notification sent to user {user_id}: {message}")
        except queue.Full:
            print(f"⚠️ Notification queue full for user {user_id}")
    else:
        print(f"📭 No active notification stream for user {user_id}")

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
    """
    try:
        # Load market data using the updated function
        df = load_market_data(symbol, asset_type, interval, outputsize)
        
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
            record = {
                "Date": row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], 'strftime') else str(row["Date"]),
                "Close": float(row["Close"]) if not pd.isna(row["Close"]) else None,
                "SMA_fast": float(row["SMA_fast"]) if not pd.isna(row["SMA_fast"]) else None,
                "SMA_slow": float(row["SMA_slow"]) if not pd.isna(row["SMA_slow"]) else None
            }
            records.append(record)
        
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "data": records
        }
        
    except Exception as e:
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

    # Load market data with asset type support
    try:
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

# -------------------------------------------------------------
# Automated Trading Bot Endpoints
# -------------------------------------------------------------

@app.post("/api/start_bot")
def start_bot(payload: dict):
    """
    Start an automated trading bot for the specified user, asset type, and symbol.
    The bot runs SMA crossover strategy and executes trades every 30 seconds.
    
    Expected payload:
    {
        "symbol": "AAPL",
        "asset_type": "stock",
        "user_id": 1
    }
    """
    symbol = payload.get("symbol")
    asset_type = payload.get("asset_type", "stock")
    user_id = payload.get("user_id")

    if not symbol or not user_id:
        raise HTTPException(status_code=400, detail="Symbol and user_id are required")

    # Check if bot is already running for this user
    if user_id in active_bots:
        return {"status": "already_running", "message": f"Bot already active for user {user_id}"}

    def bot_loop():
        """
        Main bot loop that runs SMA crossover strategy every 30 seconds
        Enhanced with MySQL database integration for real portfolio management
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
            
            print(f"🤖 Bot started for user {user_id} trading {asset_type}:{symbol}")
            print(f"💰 Current wallet: ${wallet:,.2f}")
            
            while user_id in active_bots:
                try:
                    # Fetch latest market data
                    df = load_market_data(symbol, asset_type)
                    if df is None or df.empty:
                        print(f"❌ No market data available for {asset_type}:{symbol}")
                        time.sleep(30)
                        continue
                    
                    # Calculate SMAs
                    df["SMA_fast"] = df["Close"].rolling(fast_period).mean()
                    df["SMA_slow"] = df["Close"].rolling(slow_period).mean()
                    
                    # Get the latest data point
                    latest = df.tail(1).iloc[0]
                    current_price = float(latest["Close"])
                    sma_fast = latest["SMA_fast"]
                    sma_slow = latest["SMA_slow"]
                    
                    # Skip if SMAs are not available (not enough data)
                    if pd.isna(sma_fast) or pd.isna(sma_slow):
                        print(f"⏳ Waiting for SMA data... (need at least {slow_period} data points)")
                        time.sleep(30)
                        continue
                    
                    # Get current wallet balance from database
                    current_wallet = get_user_wallet(user_id)
                    if current_wallet is None:
                        print(f"❌ Cannot get current wallet for user {user_id}")
                        time.sleep(30)
                        continue
                    
                    wallet = current_wallet
                    
                    # SMA Crossover Trading Logic with Database Integration
                    if sma_fast > sma_slow and wallet >= current_price:
                        # BUY Signal - Fast SMA above Slow SMA
                        quantity_to_buy = 1
                        cost = quantity_to_buy * current_price
                        
                        if wallet >= cost:
                            new_wallet = wallet - cost
                            
                            # Update database if MySQL is available, otherwise simulate trade
                            if MYSQL_AVAILABLE:
                                if (update_user_wallet(user_id, new_wallet) and
                                    update_portfolio(user_id, symbol, asset_type, quantity_to_buy, current_price, 'BUY') and
                                    record_order(user_id, symbol, asset_type, 'BUY', current_price, quantity_to_buy)):
                                    
                                    wallet = new_wallet
                                    trade_message = f"BUY {quantity_to_buy} {symbol} @ ${current_price:.2f}"
                                    
                                    print(f"🟢 {trade_message}")
                                    print(f"   💰 Wallet: ${wallet:,.2f}")
                                    print(f"   📊 Fast SMA: ${sma_fast:.2f} | Slow SMA: ${sma_slow:.2f}")
                                    
                                    # Send notification
                                    send_notification(user_id, trade_message)
                                else:
                                    print(f"❌ Failed to execute BUY order for user {user_id}")
                            else:
                                # Simulate trade without database
                                wallet = new_wallet
                                trade_message = f"BUY {quantity_to_buy} {symbol} @ ${current_price:.2f} (SIMULATED)"
                                
                                print(f"🟢 {trade_message}")
                                print(f"   💰 Wallet: ${wallet:,.2f}")
                                print(f"   📊 Fast SMA: ${sma_fast:.2f} | Slow SMA: ${sma_slow:.2f}")
                                
                                # Send notification
                                send_notification(user_id, trade_message)
                    
                    elif sma_fast < sma_slow:
                        # Check if user has position to sell (or simulate if MySQL not available)
                        if MYSQL_AVAILABLE:
                            portfolio = get_user_portfolio(user_id)
                            user_position = None
                            for position in portfolio:
                                if position['symbol'] == symbol and position['asset_type'] == asset_type:
                                    user_position = position
                                    break
                            has_position = user_position and user_position['quantity'] > 0
                        else:
                            # For simulation, assume we have 1 share to sell if we've done a buy before
                            has_position = True  # Simulate having position
                        
                        if has_position:
                            # SELL Signal - Fast SMA below Slow SMA
                            if MYSQL_AVAILABLE:
                                quantity_to_sell = min(1, user_position['quantity'])  # Sell 1 or remaining quantity
                                revenue = quantity_to_sell * current_price
                                new_wallet = wallet + revenue
                                
                                # Update database: wallet, portfolio, and orders
                                if (update_user_wallet(user_id, new_wallet) and
                                    update_portfolio(user_id, symbol, asset_type, quantity_to_sell, current_price, 'SELL') and
                                    record_order(user_id, symbol, asset_type, 'SELL', current_price, quantity_to_sell)):
                                    
                                    wallet = new_wallet
                                    trade_message = f"SELL {quantity_to_sell} {symbol} @ ${current_price:.2f}"
                                    print(f"🔴 {trade_message}")
                                    print(f"   💰 Wallet: ${wallet:,.2f}")
                                    print(f"   📊 Fast SMA: ${sma_fast:.2f} | Slow SMA: ${sma_slow:.2f}")
                                    
                                    # Send notification
                                    send_notification(user_id, trade_message)
                                else:
                                    print(f"❌ Failed to execute SELL order for user {user_id}")
                            else:
                                # Simulate SELL order
                                quantity_to_sell = 1  # Simulate selling 1 share
                                revenue = quantity_to_sell * current_price
                                trade_message = f"SIMULATED SELL {quantity_to_sell} {symbol} @ ${current_price:.2f}"
                                print(f"🔴 {trade_message} (SIMULATION MODE)")
                                print(f"   📊 Fast SMA: ${sma_fast:.2f} | Slow SMA: ${sma_slow:.2f}")
                                
                                # Send notification
                                send_notification(user_id, trade_message)
                        else:
                            # HOLD - No position to sell
                            if MYSQL_AVAILABLE:
                                print(f"⚪ HOLD {symbol} at ${current_price:.2f} | Wallet: ${wallet:,.2f} | No position")
                            else:
                                print(f"⚪ HOLD {symbol} at ${current_price:.2f} | No position (SIMULATION MODE)")
                            print(f"   📊 Fast SMA: ${sma_fast:.2f} | Slow SMA: ${sma_slow:.2f}")
                    
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

@app.post("/api/stop_bot")
def stop_bot(payload: dict):
    """
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
    """
    try:
        # Get wallet balance
        wallet = get_user_wallet(user_id)
        if wallet is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        # Get portfolio holdings
        portfolio = get_user_portfolio(user_id)
        total_holdings_value = sum(float(position['total_value']) for position in portfolio)
        
        # Get recent orders
        recent_orders = get_user_orders(user_id, 10)
        
        return {
            "user_id": user_id,
            "wallet_balance": wallet,
            "total_holdings_value": total_holdings_value,
            "total_portfolio_value": wallet + total_holdings_value,
            "holdings": portfolio,
            "recent_orders": recent_orders,
            "positions_count": len(portfolio)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching portfolio summary: {str(e)}")
