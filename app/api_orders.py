from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date
from typing import Dict, Any

try:
    # Try relative imports first (when imported as a module)
    from .database import get_db
    from .models import User, OrderTrade, Portfolio
except ImportError:
    # Fall back to direct imports (when running as standalone)
    from database import get_db
    from models import User, OrderTrade, Portfolio

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
    Enhanced order placement with portfolio tracking and validation
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
        
        # Find the user
        user = db.query(User).filter(User.id == order.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Calculate order total
        order_total = order.price * order.qty
        
        # Handle BUY orders
        if order.action.upper() == "BUY":
            # Check wallet balance
            if user.wallet_balance < order_total:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient balance. Available: ${user.wallet_balance:.2f}, Required: ${order_total:.2f}"
                )
            
            # Deduct from wallet
            user.wallet_balance -= order_total
            
            # Update or create portfolio holding
            portfolio = db.query(Portfolio).filter(
                Portfolio.user_id == order.user_id,
                Portfolio.symbol == order.symbol.upper(),
                Portfolio.asset_type == order.asset_type.lower()
            ).first()
            
            if portfolio:
                # Calculate new weighted average price
                total_value = (portfolio.quantity * portfolio.avg_price) + (order.qty * order.price)
                new_quantity = portfolio.quantity + order.qty
                portfolio.avg_price = total_value / new_quantity if new_quantity > 0 else 0
                portfolio.quantity = new_quantity
            else:
                # Create new portfolio holding
                portfolio = Portfolio(
                    user_id=order.user_id,
                    symbol=order.symbol.upper(),
                    asset_type=order.asset_type.lower(),
                    quantity=order.qty,
                    avg_price=order.price
                )
                db.add(portfolio)
        
        else:  # SELL order
            # Check if user has enough holdings to sell
            portfolio = db.query(Portfolio).filter(
                Portfolio.user_id == order.user_id,
                Portfolio.symbol == order.symbol.upper(),
                Portfolio.asset_type == order.asset_type.lower()
            ).first()
            
            if not portfolio or portfolio.quantity < order.qty:
                current_holdings = portfolio.quantity if portfolio else 0
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient holdings. You own {current_holdings} {order.symbol}, trying to sell {order.qty}"
                )
            
            # Update portfolio (reduce quantity)
            portfolio.quantity -= order.qty
            
            # Add sale proceeds to wallet
            user.wallet_balance += order_total
            
            # If quantity becomes zero, we can optionally keep the record with 0 quantity
            # or remove it entirely - keeping it for now to preserve avg_price history
        
        # Create the trade record with asset type
        trade = OrderTrade(
            user_id=order.user_id,
            symbol=order.symbol.upper(),
            asset_type=order.asset_type.lower(),
            date=date.today(),
            action=order.action.upper(),
            price=order.price,
            qty=order.qty
        )
        
        # Add trade and update user
        db.add(trade)
        db.commit()
        db.refresh(user)
        
        return OrderResponse(
            message=f"{order.action.upper()} order placed for {order.symbol.upper()}",
            new_balance=user.wallet_balance
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        db.rollback()
        raise
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
            # For now, use avg_price as current_price - in production you'd fetch real market data
            current_price = portfolio.avg_price  # TODO: Integrate with real market data API
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