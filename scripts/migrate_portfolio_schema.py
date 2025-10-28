#!/usr/bin/env python3
"""
Database Migration Script - Portfolio Support
Adds portfolio support to the trading bot database:
1. Add asset_type column to order_trades table
2. Create portfolios table
3. Update existing data with default asset_type
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.database import DB_URL
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the database migration"""
    try:
        # Create database engine
        engine = create_engine(DB_URL)
        
        logger.info("🔄 Starting portfolio schema migration...")
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                # 1. Add asset_type column to order_trades table
                logger.info("📋 Adding asset_type column to order_trades table...")
                
                # Check if column already exists
                result = conn.execute(text("""
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = 'order_trades' 
                    AND COLUMN_NAME = 'asset_type'
                    AND TABLE_SCHEMA = DATABASE()
                """))
                
                if not result.fetchone():
                    conn.execute(text("""
                        ALTER TABLE order_trades 
                        ADD COLUMN asset_type VARCHAR(50) DEFAULT 'stock' NOT NULL
                    """))
                    logger.info("✅ Added asset_type column to order_trades")
                else:
                    logger.info("ℹ️ asset_type column already exists in order_trades")
                
                # 2. Create portfolios table
                logger.info("📋 Creating portfolios table...")
                
                # Check if table exists
                result = conn.execute(text("""
                    SELECT TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME = 'portfolios'
                    AND TABLE_SCHEMA = DATABASE()
                """))
                
                if not result.fetchone():
                    conn.execute(text("""
                        CREATE TABLE portfolios (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            symbol VARCHAR(20) NOT NULL,
                            asset_type VARCHAR(50) NOT NULL DEFAULT 'stock',
                            quantity DECIMAL(15, 6) NOT NULL DEFAULT 0,
                            avg_price DECIMAL(15, 6) NOT NULL DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            UNIQUE KEY unique_user_symbol_asset (user_id, symbol, asset_type),
                            INDEX idx_user_id (user_id),
                            INDEX idx_symbol (symbol),
                            INDEX idx_asset_type (asset_type)
                        )
                    """))
                    logger.info("✅ Created portfolios table")
                else:
                    logger.info("ℹ️ portfolios table already exists")
                
                # 3. Update existing order_trades records with default asset_type
                logger.info("📋 Updating existing order_trades with default asset_type...")
                result = conn.execute(text("""
                    UPDATE order_trades 
                    SET asset_type = 'stock' 
                    WHERE asset_type IS NULL OR asset_type = ''
                """))
                updated_rows = result.rowcount
                logger.info(f"✅ Updated {updated_rows} existing order_trades records")
                
                # 4. Verify the changes
                logger.info("📋 Verifying database schema...")
                
                # Check order_trades structure
                result = conn.execute(text("DESCRIBE order_trades"))
                order_trades_columns = [row[0] for row in result.fetchall()]
                logger.info(f"📋 order_trades columns: {', '.join(order_trades_columns)}")
                
                # Check portfolios structure
                result = conn.execute(text("DESCRIBE portfolios"))
                portfolio_columns = [row[0] for row in result.fetchall()]
                logger.info(f"📋 portfolios columns: {', '.join(portfolio_columns)}")
                
                # Count existing data
                result = conn.execute(text("SELECT COUNT(*) FROM order_trades"))
                order_count = result.fetchone()[0]
                
                result = conn.execute(text("SELECT COUNT(*) FROM portfolios"))
                portfolio_count = result.fetchone()[0]
                
                logger.info(f"📊 Database status:")
                logger.info(f"   - order_trades records: {order_count}")
                logger.info(f"   - portfolios records: {portfolio_count}")
                
                # Commit transaction
                trans.commit()
                logger.info("✅ SUCCESS: Portfolio schema migration completed!")
                
                return True
                
            except Exception as e:
                # Rollback on error
                trans.rollback()
                logger.error(f"❌ ERROR during migration: {str(e)}")
                raise e
                
    except Exception as e:
        logger.error(f"❌ FAILED: Migration failed: {str(e)}")
        return False
    
    finally:
        engine.dispose()

def main():
    """Main function"""
    logger.info("🚀 Starting Trading Bot Portfolio Schema Migration")
    logger.info("=" * 60)
    
    success = run_migration()
    
    if success:
        logger.info("=" * 60)
        logger.info("🎉 Migration completed successfully!")
        logger.info("💡 You can now restart your FastAPI server")
        return 0
    else:
        logger.error("=" * 60)
        logger.error("💥 Migration failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())