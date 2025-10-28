#!/usr/bin/env python3
"""
Initialize database tables
Creates all tables defined in models.py
"""

import sys
import os

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import Base, engine
from sqlalchemy import text

def init_db():
    """Create all database tables"""
    try:
        print("🔄 Creating/updating database tables...")
        Base.metadata.create_all(bind=engine)
        
        # Check what tables were created/exist
        with engine.connect() as connection:
            result = connection.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result]
        
        print("✅ SUCCESS: Database tables ready!")
        print("📋 Available tables:")
        expected_tables = ["market_data", "signals", "trades", "episodes", "training_runs", "models", "users", "order_trades", "portfolios"]
        
        for table in expected_tables:
            if table in tables:
                print(f"  ✅ {table}")
            else:
                print(f"  ❌ {table} (missing)")
        
        # Check users table structure
        if "users" in tables:
            print("\n📋 Users table structure:")
            result = connection.execute(text("DESCRIBE users"))
            for row in result:
                print(f"  - {row[0]}: {row[1]}")
        
        return True
    except Exception as e:
        print(f"❌ ERROR: Failed to create tables: {e}")
        print("💡 TIP: Make sure MySQL is running and database 'trading_bot' exists")
        return False

if __name__ == "__main__":
    success = init_db()
    if success:
        print("\nDatabase initialization completed successfully!")
    else:
        print("\nDatabase initialization failed!")
        sys.exit(1)
