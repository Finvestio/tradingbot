#!/usr/bin/env python3
"""
Add sample users to the database for testing
"""

import sys
import os

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_db
from app.models import User

def add_sample_users():
    """Add some sample users for testing"""
    try:
        db = next(get_db())
        
        # Check if users already exist
        existing_users = db.query(User).count()
        if existing_users > 0:
            print(f"Found {existing_users} existing users. Skipping user creation.")
            return True
        
        # Create sample users
        users = [
            User(username="trader1", email="trader1@example.com", wallet_balance=100000.0),
            User(username="investor1", email="investor1@example.com", wallet_balance=50000.0),
            User(username="daytrader", email="daytrader@example.com", wallet_balance=25000.0)
        ]
        
        for user in users:
            db.add(user)
        
        db.commit()
        
        print("SUCCESS: Sample users created successfully!")
        print("Users created:")
        for user in users:
            print(f"- {user.username} ({user.email}) - Balance: ${user.wallet_balance:,.2f}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to create sample users: {e}")
        if 'db' in locals():
            db.rollback()
        return False
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    success = add_sample_users()
    if success:
        print("\nSample users added successfully!")
    else:
        print("\nFailed to add sample users!")
        sys.exit(1)