"""
Create bot_trades table for storing bot trading history.
"""
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

DB_CFG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "trading_bot")
}

def create_bot_trades_table():
    """Create bot_trades table if it doesn't exist."""
    cnx = mysql.connector.connect(**DB_CFG)
    cur = cnx.cursor()
    
    # Create bot_trades table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_trades (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            asset_type VARCHAR(20) DEFAULT 'stock',
            action VARCHAR(10) NOT NULL,
            price DECIMAL(15, 2) NOT NULL,
            quantity INT DEFAULT 1,
            reward DECIMAL(15, 4) DEFAULT 0,
            equity DECIMAL(15, 2) DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_symbol (user_id, symbol),
            INDEX idx_timestamp (timestamp)
        )
    """)
    
    cnx.commit()
    print("✅ bot_trades table created successfully!")
    
    # Check if table exists
    cur.execute("SHOW TABLES LIKE 'bot_trades'")
    result = cur.fetchone()
    if result:
        print(f"✅ Verified: {result[0]} table exists")
        
        # Show table structure
        cur.execute("DESCRIBE bot_trades")
        columns = cur.fetchall()
        print("\n📋 Table structure:")
        for col in columns:
            print(f"   {col[0]}: {col[1]}")
    
    cur.close()
    cnx.close()

if __name__ == "__main__":
    create_bot_trades_table()
