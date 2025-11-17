from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date
from typing import Dict, Any

try:
    # Try relative imports first (when imported as a module)
    from .database import get_db
    from .models import User, OrderTrade, Portfolio
    from .broker.portfolio import PortfolioManager
except ImportError:
    # Fall back to direct imports (when running as standalone)
    from database import get_db
    from models import User, OrderTrade, Portfolio
    from broker.portfolio import PortfolioManager

# Create the router
router = APIRouter(prefix="/api/orders")

# Pydantic models for request/response
class OrderRequest(BaseModel):
    user_id: int
    symbol: str
    asset_type: str  # 'stock', 'crypto', 'derivative'
    action: str  # BUY or SELL
    qty: float
    price: float

class OrderResponse(BaseModel):
    message: str
    new_balance: float
    portfolio_updated: bool = True

class PortfolioHolding(BaseModel):
    symbol: str
    asset_type: str
    quantity: float
    avg_price: float
    current_price: float = 0.0  # Will be populated from market data
    market_value: float = 0.0   # quantity * current_price
    unrealized_pnl: float = 0.0  # (current_price - avg_price) * quantity

class PortfolioSummary(BaseModel):
    user_id: int
    wallet_balance: float
    total_market_value: float
    total_unrealized_pnl: float
    holdings: list[PortfolioHolding]

@router.post("/place", response_model=OrderResponse)
async def place_order(order: OrderRequest, db: Session = Depends(get_db)):
    """
    Enhanced order placement using unified PortfolioManager.execute_trade method
    Supports multiple asset types: stock, crypto, derivative
    """
    try:
        # Input validation
        if order.action.upper() not in ["BUY", "SELL"]:
            raise HTTPException(status_code=400, detail="Action must be BUY or SELL")
        
        if order.asset_type.lower() not in ["stock", "crypto", "derivative"]:
            raise HTTPException(status_code=400, detail="Asset type must be: stock, crypto, or derivative")
        
        if order.qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        
        if order.price <= 0:
            raise HTTPException(status_code=400, detail="Price must be positive")
        
        # Use unified portfolio manager for trade execution
        portfolio_manager = PortfolioManager(db)
        
        # Execute trade using the same method as bot trades
        result = portfolio_manager.execute_trade(
            user_id=order.user_id,
            symbol=order.symbol,
            action=order.action,
            quantity=order.qty,
            price=order.price,
            asset_type=order.asset_type
        )
        
        return OrderResponse(
            message=result["message"],
            new_balance=result["new_wallet_balance"]
        )
        
    except ValueError as e:
        # Handle business logic errors (insufficient balance, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle any other exceptions
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/user/{user_id}/balance")
async def get_user_balance(user_id: int, db: Session = Depends(get_db)):
    """
    Get user's current wallet balance
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"user_id": user_id, "balance": user.wallet_balance}

@router.get("/user/{user_id}/trades")
async def get_user_trades(user_id: int, db: Session = Depends(get_db)):
    """
    Get all trades for a user
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    trades = db.query(OrderTrade).filter(OrderTrade.user_id == user_id).all()
    
    return {
        "user_id": user_id,
        "trades": [
            {
                "id": trade.id,
                "symbol": trade.symbol,
                "date": trade.date,
                "action": trade.action,
                "price": trade.price,
                "qty": trade.qty,
                "total": trade.price * trade.qty
            }
            for trade in trades
        ]
    }

# Additional endpoints needed by Angular frontend

@router.get("/")
async def get_all_orders(db: Session = Depends(get_db)):
    """
    Get all orders in the system
    """
    trades = db.query(OrderTrade).all()
    
    return [
        {
            "id": trade.id,
            "user_id": trade.user_id,
            "symbol": trade.symbol,
            "action": trade.action,
            "price": trade.price,
            "qty": trade.qty,
            "total": trade.price * trade.qty,
            "created_at": trade.date.isoformat() if trade.date else None
        }
        for trade in trades
    ]

@router.get("/users")  
async def get_all_users(db: Session = Depends(get_db)):
    """
    Get all users in the system
    """
    users = db.query(User).all()
    
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "wallet_balance": user.wallet_balance,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        for user in users
    ]

@router.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """
    Get a specific user by ID
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "wallet_balance": user.wallet_balance,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }

class UserCreateRequest(BaseModel):
    username: str
    email: str
    wallet_balance: float = 100000

@router.post("/users")
async def create_user(user_data: UserCreateRequest, db: Session = Depends(get_db)):
    """
    Create a new user
    """
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Create new user
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        wallet_balance=user_data.wallet_balance
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "wallet_balance": new_user.wallet_balance,
            "created_at": new_user.created_at.isoformat() if new_user.created_at else None
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")

@router.get("/user/{user_id}")
async def get_user_orders(user_id: int, db: Session = Depends(get_db)):
    """
    Get all orders for a specific user (alternative endpoint)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    trades = db.query(OrderTrade).filter(OrderTrade.user_id == user_id).all()
    
    return [
        {
            "id": trade.id,
            "user_id": trade.user_id,
            "symbol": trade.symbol,
            "asset_type": getattr(trade, 'asset_type', 'stock'),  # Handle legacy trades
            "action": trade.action,
            "price": trade.price,
            "qty": trade.qty,
            "total": trade.price * trade.qty,
            "created_at": trade.date.isoformat() if trade.date else None
        }
        for trade in trades
    ]

@router.get("/user/{user_id}/portfolio", response_model=PortfolioSummary)
async def get_user_portfolio(user_id: int, db: Session = Depends(get_db)):
    """
    Get user's complete portfolio including wallet balance, holdings, and valuations
    """
    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get all portfolio holdings for the user
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
    
    holdings = []
    total_market_value = 0.0
    total_unrealized_pnl = 0.0
    
    for portfolio in portfolios:
        if portfolio.quantity > 0:  # Only include holdings with positive quantity
            # Fetch REAL-TIME price from Twelve Data API
            current_price = portfolio.avg_price  # Default fallback
            price_fetched = False
            
            try:
                from app.data.loader import fetch_realtime_price
                realtime_data = fetch_realtime_price(portfolio.symbol, portfolio.asset_type)
                current_price = float(realtime_data["price"])
                price_fetched = True
            except Exception as e:
                # Fallback to avg_price if real-time fetch fails
                current_price = portfolio.avg_price
                price_fetched = False
            
            market_value = portfolio.quantity * current_price
            unrealized_pnl = (current_price - portfolio.avg_price) * portfolio.quantity
            
            holdings.append(PortfolioHolding(
                symbol=portfolio.symbol,
                asset_type=portfolio.asset_type,
                quantity=portfolio.quantity,
                avg_price=portfolio.avg_price,
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl
            ))
            
            total_market_value += market_value
            total_unrealized_pnl += unrealized_pnl
    
    return PortfolioSummary(
        user_id=user_id,
        wallet_balance=user.wallet_balance,
        total_market_value=total_market_value,
        total_unrealized_pnl=total_unrealized_pnl,
        holdings=holdings
    )

@router.get("/user/{user_id}/portfolio/enhanced")
async def get_enhanced_portfolio(user_id: int, db: Session = Depends(get_db)):
    """
    Get enhanced portfolio summary with advanced metrics using PortfolioManager
    """
    try:
        portfolio_manager = PortfolioManager(db)
        summary = await portfolio_manager.get_portfolio_summary(user_id)
        
        # Convert to dict for JSON response
        return {
            "user_id": summary.user_id,
            "wallet_balance": summary.wallet_balance,
            "total_market_value": summary.total_market_value,
            "total_portfolio_value": summary.total_portfolio_value,
            "total_unrealized_pnl": summary.total_unrealized_pnl,
            "total_unrealized_pnl_percent": summary.total_unrealized_pnl_percent,
            "positions_count": summary.positions_count,
            "diversification_score": summary.diversification_score,
            "positions": [
                {
                    "symbol": pos.symbol,
                    "asset_type": pos.asset_type,
                    "quantity": pos.quantity,
                    "avg_price": pos.avg_price,
                    "current_price": pos.current_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_percent": pos.unrealized_pnl_percent,
                    "weight": pos.weight
                }
                for pos in summary.positions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio summary: {str(e)}")

@router.get("/user/{user_id}/portfolio/risk")
async def get_portfolio_risk_metrics(user_id: int, db: Session = Depends(get_db)):
    """
    Get comprehensive risk metrics for user's portfolio
    """
    try:
        portfolio_manager = PortfolioManager(db)
        risk_metrics = await portfolio_manager.get_risk_metrics(user_id)
        return risk_metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get risk metrics: {str(e)}")

@router.get("/user/{user_id}/portfolio/performance")
async def get_portfolio_performance(user_id: int, days: int = 30, db: Session = Depends(get_db)):
    """
    Get portfolio performance metrics over specified time period
    """
    try:
        portfolio_manager = PortfolioManager(db)
        performance = portfolio_manager.get_portfolio_performance(user_id, days)
        return performance
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance metrics: {str(e)}")

@router.get("/user/{user_id}/position/{symbol}/{asset_type}/risk")
async def get_position_risk(user_id: int, symbol: str, asset_type: str, db: Session = Depends(get_db)):
    """
    Get risk metrics for a specific position
    """
    try:
        portfolio_manager = PortfolioManager(db)
        risk_metrics = portfolio_manager.get_position_risk_metrics(user_id, symbol, asset_type)
        return risk_metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get position risk: {str(e)}")