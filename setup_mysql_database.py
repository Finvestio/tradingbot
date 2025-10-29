#!/usr/bin/env python3
"""
Database setup script for the enhanced trading bot with MySQL integration
This script creates the necessary database tables and populates initial data
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_database_and_tables():
    """
    Create trading_bot database and all necessary tables
    """
    try:
        # First, connect without specifying database to create it
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "")
        )
        
        cursor = connection.cursor()
        
        # Create database
        print("🔧 Creating trading_bot database...")
        cursor.execute("CREATE DATABASE IF NOT EXISTS trading_bot")
        cursor.execute("USE trading_bot")
        
        # Create users table
        print("🔧 Creating users table...")
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
        print("🔧 Creating portfolio table...")
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
        print("🔧 Creating orders table...")
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
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_timestamp (user_id, timestamp),
                INDEX idx_symbol (symbol)
            )
        """)
        
        connection.commit()
        print("✅ Database tables created successfully!")
        
        return connection
        
    except Error as e:
        print(f"❌ Error creating database: {e}")
        return None

def populate_sample_data(connection):
    """
    Populate database with sample users for testing
    """
    try:
        cursor = connection.cursor()
        
        # Sample users
        sample_users = [
            ("yassinehassine", "yassinehassine@example.com", 100000.00),
            ("alice_trader", "alice@tradingbot.com", 150000.00),
            ("bob_investor", "bob@tradingbot.com", 75000.00),
            ("charlie_crypto", "charlie@tradingbot.com", 200000.00),
            ("diana_stocks", "diana@tradingbot.com", 120000.00)
        ]
        
        print("👥 Adding sample users...")
        for username, email, balance in sample_users:
            try:
                cursor.execute("""
                    INSERT IGNORE INTO users (username, email, wallet_balance)
                    VALUES (%s, %s, %s)
                """, (username, email, balance))
                print(f"   ✅ Added user: {username}")
            except Error as e:
                print(f"   ⚠️ User {username} might already exist: {e}")
        
        connection.commit()
        print("✅ Sample data populated successfully!")
        
    except Error as e:
        print(f"❌ Error populating sample data: {e}")

def verify_setup(connection):
    """
    Verify the database setup by running test queries
    """
    try:
        cursor = connection.cursor(dictionary=True)
        
        print("🔍 Verifying database setup...")
        
        # Check users
        cursor.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()['count']
        print(f"   👥 Users: {user_count}")
        
        # Check tables exist
        cursor.execute("SHOW TABLES")
        tables = [table for table_dict in cursor.fetchall() for table in table_dict.values()]
        expected_tables = ['users', 'portfolio', 'orders']
        
        for table in expected_tables:
            if table in tables:
                print(f"   ✅ Table '{table}' exists")
            else:
                print(f"   ❌ Table '{table}' missing")
        
        # Display sample users
        cursor.execute("SELECT username, email, wallet_balance FROM users LIMIT 5")
        users = cursor.fetchall()
        
        print("\n📋 Sample Users:")
        for user in users:
            print(f"   • {user['username']} ({user['email']}) - ${user['wallet_balance']:,.2f}")
        
        print("✅ Database verification completed!")
        
    except Error as e:
        print(f"❌ Error verifying setup: {e}")

def main():
    """
    Main setup function
    """
    print("🚀 Trading Bot Database Setup")
    print("=" * 40)
    
    # Create database and tables
    connection = create_database_and_tables()
    if not connection:
        print("❌ Failed to create database. Exiting.")
        return
    
    # Populate sample data
    populate_sample_data(connection)
    
    # Verify setup
    verify_setup(connection)
    
    # Close connection
    if connection:
        connection.close()
    
    print("\n🎉 Database setup completed!")
    print("\n📝 Next Steps:")
    print("1. Start the FastAPI server: uvicorn app.api:app --reload --port 8081")
    print("2. Start the Angular dev server: ng serve")
    print("3. Navigate to http://localhost:4200")
    print("4. Go to Strategy & Analysis tab and start the trading bot!")
    print("5. Check Order Management tab for real-time portfolio updates")

if __name__ == "__main__":
    main()