from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Date, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

try:
    # Try relative import first (when imported as a module)
    from .database import Base
except ImportError:
    # Fall back to direct import (when running as standalone)
    from database import Base

# MarketData Model
class MarketData(Base):
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    close = Column(Float, nullable=False)

# Signal Model
class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    fast = Column(Integer, nullable=False)
    slow = Column(Integer, nullable=False)
    signal = Column(Integer, nullable=False)

# Trade Model
class Trade(Base):
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    action = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    qty = Column(Float, nullable=False)
    episode_id = Column(Integer, ForeignKey("episodes.id"))

# Episode Model
class Episode(Base):
    __tablename__ = "episodes"
    
    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    notes = Column(Text)

# TrainingRun Model
class TrainingRun(Base):
    __tablename__ = "training_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    algo = Column(String(50), nullable=False)
    params = Column(JSON)
    reward = Column(Float)
    notes = Column(Text)

# Model Model
class Model(Base):
    __tablename__ = "models"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    algo = Column(String(50), nullable=False)
    params = Column(JSON)
    path = Column(String(255), nullable=False)
    metrics = Column(JSON)

# User Model for Order Management
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    wallet_balance = Column(Float, default=100000.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    trades = relationship("OrderTrade", back_populates="user")
    portfolios = relationship("Portfolio", back_populates="user")

# Portfolio Model for Multi-Asset Holdings
class Portfolio(Base):
    __tablename__ = "portfolio"  # Match MySQL table name (singular)
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    symbol = Column(String(20), nullable=False)
    asset_type = Column(String(20), nullable=False)  # 'stock', 'crypto', 'derivative', etc.
    quantity = Column(Float, default=0.0)
    avg_price = Column(Float, default=0.0)
    user = relationship("User", back_populates="portfolios")

# Trade Model for Order Management (renamed to avoid conflict)
class OrderTrade(Base):
    __tablename__ = "order_trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    symbol = Column(String(20))  # Increased to 20 to support crypto symbols
    asset_type = Column(String(20), default="stock")  # Add asset type to trades
    date = Column(Date)
    action = Column(String(4))  # BUY / SELL
    price = Column(Float)
    qty = Column(Float)
    user = relationship("User", back_populates="trades")

# MySQL Trading Bot Models (for direct MySQL connector usage)
# These are for documentation - actual operations use mysql.connector directly

class BotOrder:
    """
    MySQL Orders table structure:
    - id: INT AUTO_INCREMENT PRIMARY KEY
    - user_id: INT NOT NULL (FK to users.id)
    - symbol: VARCHAR(20) NOT NULL
    - asset_type: ENUM('stock', 'crypto', 'derivative') NOT NULL
    - side: ENUM('BUY', 'SELL') NOT NULL
    - price: DECIMAL(10,2) NOT NULL
    - quantity: INT NOT NULL
    - timestamp: DATETIME DEFAULT CURRENT_TIMESTAMP
    """
    pass

class BotPortfolio:
    """
    MySQL Portfolio table structure:
    - id: INT AUTO_INCREMENT PRIMARY KEY  
    - user_id: INT NOT NULL (FK to users.id)
    - symbol: VARCHAR(20) NOT NULL
    - asset_type: ENUM('stock', 'crypto', 'derivative') NOT NULL
    - quantity: INT DEFAULT 0
    - avg_price: DECIMAL(10,2) DEFAULT 0.00
    - created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    - updated_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    - UNIQUE KEY: (user_id, symbol, asset_type)
    """
    pass

class BotUser:
    """
    MySQL Users table structure (enhanced):
    - id: INT AUTO_INCREMENT PRIMARY KEY
    - username: VARCHAR(50) NOT NULL UNIQUE
    - email: VARCHAR(100) NOT NULL UNIQUE  
    - wallet_balance: DECIMAL(15,2) DEFAULT 100000.00
    - created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    - updated_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    """
    pass
