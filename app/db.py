"""
Database connection and utilities for MySQL integration
"""
try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_AVAILABLE = True
except ImportError:
    print("⚠️ MySQL connector not available. Install with: pip install mysql-connector-python")
    MYSQL_AVAILABLE = False
    # Create dummy Error class for fallback
    class Error(Exception):
        pass

import os
from typing import Optional
from contextlib import contextmanager

def get_db_connection():
    """
    Create and return a MySQL database connection
    """
    if not MYSQL_AVAILABLE:
        print("⚠️ MySQL not available - using fallback mode")
        return None
    
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "trading_bot"),
            autocommit=False
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

@contextmanager
def get_db_cursor(dictionary=True):
    """
    Context manager for database operations
    """
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=dictionary)
            yield cursor, connection
        else:
            yield None, None
    except Error as e:
        print(f"Database error: {e}")
        if connection:
            connection.rollback()
        yield None, None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_db():
    """
    Simple database connection getter for backward compatibility
    """
    return get_db_connection()

def init_database():
    """
    Initialize database tables if they don't exist
    """
    if not MYSQL_AVAILABLE:
        print("⚠️ MySQL not available - skipping database initialization")
        return False
        
    with get_db_cursor() as (cursor, connection):
        if cursor is None:
            print("❌ Cannot connect to database to initialize tables")
            return False
        
        try:
            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    wallet_balance DECIMAL(15,2) DEFAULT 100000.00,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            
            # Create portfolio table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    asset_type ENUM('stock', 'crypto', 'derivative') NOT NULL,
                    quantity INT DEFAULT 0,
                    avg_price DECIMAL(10,2) DEFAULT 0.00,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_position (user_id, symbol, asset_type)
                )
            """)
            
            # Create orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    asset_type ENUM('stock', 'crypto', 'derivative') NOT NULL,
                    side ENUM('BUY', 'SELL') NOT NULL,
                    price DECIMAL(10,2) NOT NULL,
                    quantity INT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            connection.commit()
            print("✅ Database tables initialized successfully")
            return True
            
        except Error as e:
            print(f"❌ Error initializing database: {e}")
            connection.rollback()
            return False

def update_user_wallet(user_id: int, new_balance: float) -> bool:
    """
    Update user's wallet balance
    """
    if not MYSQL_AVAILABLE:
        print(f"⚠️ Mock update: User {user_id} wallet to ${new_balance:,.2f}")
        return True
        
    with get_db_cursor() as (cursor, connection):
        if cursor is None:
            return False
        
        try:
            cursor.execute(
                "UPDATE users SET wallet_balance = %s WHERE id = %s",
                (new_balance, user_id)
            )
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"❌ Error updating wallet: {e}")
            connection.rollback()
            return False

def get_user_wallet(user_id: int) -> Optional[float]:
    """
    Get user's current wallet balance
    """
    if not MYSQL_AVAILABLE:
        # Return mock wallet balance
        return 100000.00
        
    with get_db_cursor() as (cursor, connection):
        if cursor is None:
            return None
        
        try:
            cursor.execute(
                "SELECT wallet_balance FROM users WHERE id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            return float(result['wallet_balance']) if result else None
        except Error as e:
            print(f"❌ Error getting wallet: {e}")
            return None

def update_portfolio(user_id: int, symbol: str, asset_type: str, quantity_change: int, price: float, side: str) -> bool:
    """
    Update portfolio position for a trade
    """
    if not MYSQL_AVAILABLE:
        print(f"⚠️ Mock portfolio update: User {user_id} {side} {quantity_change} {symbol} @ ${price}")
        return True
        
    with get_db_cursor() as (cursor, connection):
        if cursor is None:
            return False
        
        try:
            if side == 'BUY':
                # Insert or update portfolio position for buy
                cursor.execute("""
                    INSERT INTO portfolio (user_id, symbol, asset_type, quantity, avg_price)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        avg_price = ((avg_price * quantity) + (%s * %s)) / (quantity + %s),
                        quantity = quantity + %s
                """, (user_id, symbol, asset_type, quantity_change, price, price, quantity_change, quantity_change, quantity_change))
            
            elif side == 'SELL':
                # Update portfolio position for sell
                cursor.execute("""
                    UPDATE portfolio 
                    SET quantity = quantity - %s
                    WHERE user_id = %s AND symbol = %s AND asset_type = %s
                """, (quantity_change, user_id, symbol, asset_type))
                
                # Remove position if quantity becomes 0 or less
                cursor.execute("""
                    DELETE FROM portfolio 
                    WHERE user_id = %s AND symbol = %s AND asset_type = %s AND quantity <= 0
                """, (user_id, symbol, asset_type))
            
            connection.commit()
            return True
            
        except Error as e:
            print(f"❌ Error updating portfolio: {e}")
            connection.rollback()
            return False

def record_order(user_id: int, symbol: str, asset_type: str, side: str, price: float, quantity: int) -> bool:
    """
    Record a trade order in the orders table
    """
    if not MYSQL_AVAILABLE:
        print(f"⚠️ Mock order record: User {user_id} {side} {quantity} {symbol} @ ${price}")
        return True
        
    with get_db_cursor() as (cursor, connection):
        if cursor is None:
            return False
        
        try:
            cursor.execute("""
                INSERT INTO orders (user_id, symbol, asset_type, side, price, quantity, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (user_id, symbol, asset_type, side, price, quantity))
            
            connection.commit()
            return True
            
        except Error as e:
            print(f"❌ Error recording order: {e}")
            connection.rollback()
            return False

def get_user_portfolio(user_id: int):
    """
    Get user's current portfolio positions
    """
    if not MYSQL_AVAILABLE:
        # Return mock empty portfolio
        return []
        
    with get_db_cursor() as (cursor, connection):
        if cursor is None:
            return []
        
        try:
            cursor.execute("""
                SELECT symbol, asset_type, quantity, avg_price,
                       (quantity * avg_price) as total_value
                FROM portfolio 
                WHERE user_id = %s AND quantity > 0
                ORDER BY symbol
            """, (user_id,))
            
            return cursor.fetchall() or []
            
        except Error as e:
            print(f"❌ Error getting portfolio: {e}")
            return []

def get_user_orders(user_id: int, limit: int = 50):
    """
    Get user's recent orders
    """
    if not MYSQL_AVAILABLE:
        # Return mock empty orders
        return []
        
    with get_db_cursor() as (cursor, connection):
        if cursor is None:
            return []
        
        try:
            cursor.execute("""
                SELECT id, symbol, asset_type, side, price, quantity, timestamp
                FROM orders 
                WHERE user_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (user_id, limit))
            
            return cursor.fetchall() or []
            
        except Error as e:
            print(f"❌ Error getting orders: {e}")
            return []