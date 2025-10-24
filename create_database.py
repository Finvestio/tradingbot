#!/usr/bin/env python3
"""
Create the trading_bot database if it doesn't exist
Run this before the main test
"""

import pymysql
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_database():
    """Create the trading_bot database if it doesn't exist"""
    try:
        # Connect to MySQL server (without specifying database)
        connection = pymysql.connect(
            host='localhost',
            user='root',
            password='',  # Default XAMPP MySQL has no password for root
            charset='utf8mb4'
        )
        
        with connection.cursor() as cursor:
            # Create database if it doesn't exist
            cursor.execute("CREATE DATABASE IF NOT EXISTS trading_bot")
            cursor.execute("USE trading_bot")
            print("✅ Database 'trading_bot' created/verified successfully")
            
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        print("Make sure XAMPP MySQL is running and accessible")
        return False

if __name__ == "__main__":
    if create_database():
        print("🎉 Database setup completed successfully!")
    else:
        print("❌ Database setup failed!")
        exit(1)