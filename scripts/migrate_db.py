#!/usr/bin/env python3
"""
Database Migration Script - Add email and created_at to users table
This script adds missing columns to existing tables to match the updated models.
"""

import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import engine
from sqlalchemy import text

def migrate_database():
    """Add missing columns to users table"""
    try:
        with engine.connect() as connection:
            # Start a transaction
            trans = connection.begin()
            
            try:
                print("🔄 Checking users table structure...")
                
                # Check if email column exists
                result = connection.execute(text("SHOW COLUMNS FROM users LIKE 'email'"))
                if not result.fetchone():
                    print("➕ Adding 'email' column to users table...")
                    connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(100) UNIQUE"))
                else:
                    print("✅ 'email' column already exists")
                
                # Check if created_at column exists
                result = connection.execute(text("SHOW COLUMNS FROM users LIKE 'created_at'"))
                if not result.fetchone():
                    print("➕ Adding 'created_at' column to users table...")
                    connection.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
                else:
                    print("✅ 'created_at' column already exists")
                
                # Update existing users with default email if needed
                print("🔄 Updating existing users with default values...")
                connection.execute(text("""
                    UPDATE users 
                    SET email = CONCAT(username, '@example.com'),
                        created_at = COALESCE(created_at, NOW())
                    WHERE email IS NULL OR email = ''
                """))
                
                # Commit the transaction
                trans.commit()
                print("✅ SUCCESS: Database migration completed successfully!")
                return True
                
            except Exception as e:
                # Rollback on error
                trans.rollback()
                print(f"❌ ERROR during migration: {e}")
                return False
                
    except Exception as e:
        print(f"❌ ERROR: Failed to connect to database: {e}")
        return False

def show_table_structure():
    """Show the current users table structure"""
    try:
        with engine.connect() as connection:
            print("\n📋 Current users table structure:")
            result = connection.execute(text("DESCRIBE users"))
            for row in result:
                print(f"  - {row[0]}: {row[1]} {row[2]} {row[3]} {row[4]} {row[5]}")
    except Exception as e:
        print(f"❌ ERROR: Could not show table structure: {e}")

if __name__ == "__main__":
    print("🚀 Starting database migration...")
    print("📊 Target: Add email and created_at columns to users table")
    print("-" * 60)
    
    success = migrate_database()
    
    if success:
        show_table_structure()
        print("\n✅ Migration completed! You can now start the servers.")
    else:
        print("\n❌ Migration failed! Please check the errors above.")
        sys.exit(1)