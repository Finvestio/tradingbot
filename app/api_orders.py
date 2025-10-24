from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date
from typing import Dict, Any

try:
    # Try relative imports first (when imported as a module)
    from .database import get_db
    from .models import User, OrderTrade
except ImportError:
    # Fall back to direct imports (when running as standalone)
    from database import get_db
    from models import User, OrderTrade

# Create the router
router = APIRouter(prefix="/api/orders")

# Pydantic models for request/response
class OrderRequest(BaseModel):
    user_id: int
    symbol: str
    action: str  # BUY or SELL
    qty: float
    price: float

class OrderResponse(BaseModel):
    message: str
    new_balance: float

@router.post("/place", response_model=OrderResponse)
async def place_order(order: OrderRequest, db: Session = Depends(get_db)):
    """
    Place a buy or sell order for a user
    """
    try:
        # Validate action
        if order.action.upper() not in ["BUY", "SELL"]:
            raise HTTPException(status_code=400, detail="Action must be BUY or SELL")
        
        # Find the user
        user = db.query(User).filter(User.id == order.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Calculate order total
        order_total = order.price * order.qty
        
        # For BUY orders, check wallet balance
        if order.action.upper() == "BUY":
            if user.wallet_balance < order_total:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient balance. Available: ${user.wallet_balance:.2f}, Required: ${order_total:.2f}"
                )
            # Deduct from wallet for BUY
            user.wallet_balance -= order_total
        else:  # SELL order
            # Add to wallet for SELL
            user.wallet_balance += order_total
        
        # Create the trade record
        trade = OrderTrade(
            user_id=order.user_id,
            symbol=order.symbol.upper(),
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
            "action": trade.action,
            "price": trade.price,
            "qty": trade.qty,
            "total": trade.price * trade.qty,
            "created_at": trade.date.isoformat() if trade.date else None
        }
        for trade in trades
    ]