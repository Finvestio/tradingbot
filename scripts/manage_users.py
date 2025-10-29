#!/usr/bin/env python3
"""
User Management Script
Check existing users and optionally add sample users to the database
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import User
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_and_add_users():
    """Check existing users and add sample users if database is empty"""
    try:
        db = SessionLocal()
        
        # Check existing users
        existing_users = db.query(User).all()
        logger.info(f"📊 Found {len(existing_users)} existing users in database:")
        
        for user in existing_users:
            logger.info(f"   👤 {user.username} (ID: {user.id}) - Wallet: ${user.wallet_balance:,.2f} - Email: {user.email}")
        
        if len(existing_users) == 0:
            logger.info("📝 No users found. Adding sample users...")
            
            # Create sample users
            sample_users = [
                User(username="alice", email="alice@trading.com", wallet_balance=105000.0),
                User(username="bob", email="bob@trading.com", wallet_balance=52000.0),
                User(username="charlie", email="charlie@trading.com", wallet_balance=76000.0),
                User(username="diana", email="diana@trading.com", wallet_balance=98500.0),
                User(username="eve", email="eve@trading.com", wallet_balance=123000.0),
            ]
            
            for user in sample_users:
                db.add(user)
            
            db.commit()
            logger.info("✅ Sample users added successfully!")
            
            # Show the new users
            new_users = db.query(User).all()
            logger.info(f"📊 Database now has {len(new_users)} users:")
            for user in new_users:
                logger.info(f"   👤 {user.username} (ID: {user.id}) - Wallet: ${user.wallet_balance:,.2f}")
        
        else:
            logger.info("✅ Users already exist in database. No changes needed.")
            
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        return False
    finally:
        db.close()
    
    return True

def main():
    logger.info("🚀 Starting User Management Script")
    logger.info("=" * 60)
    
    success = check_and_add_users()
    
    if success:
        logger.info("=" * 60)
        logger.info("🎉 User management completed!")
        logger.info("💡 You can now use the /api/users endpoint to fetch real users")
    else:
        logger.error("💥 User management failed!")

if __name__ == "__main__":
    main()