#!/usr/bin/env python3
"""
Final Database Fix - Ensure email column is NOT NULL and properly constrained
"""

import sys
import os

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import engine
from sqlalchemy import text

def fix_email_constraints():
    """Fix email column to match SQLAlchemy model expectations"""
    try:
        with engine.connect() as connection:
            trans = connection.begin()
            
            try:
                print("🔄 Fixing email column constraints...")
                
                # First, update any NULL emails with default values
                result = connection.execute(text("""
                    UPDATE users 
                    SET email = CONCAT(username, '@example.com')
                    WHERE email IS NULL OR email = ''
                """))
                
                print(f"📝 Updated {result.rowcount} users with default emails")
                
                # Make email NOT NULL and ensure UNIQUE constraint
                print("🔧 Making email column NOT NULL...")
                connection.execute(text("ALTER TABLE users MODIFY COLUMN email VARCHAR(100) NOT NULL UNIQUE"))
                
                # Also fix username to be NOT NULL as expected by model
                print("🔧 Making username column NOT NULL...")
                connection.execute(text("ALTER TABLE users MODIFY COLUMN username VARCHAR(50) NOT NULL UNIQUE"))
                
                trans.commit()
                print("✅ SUCCESS: Email and username constraints fixed!")
                return True
                
            except Exception as e:
                trans.rollback()
                print(f"❌ ERROR during constraint fix: {e}")
                return False
                
    except Exception as e:
        print(f"❌ ERROR: Failed to connect to database: {e}")
        return False

def show_final_structure():
    """Show the final users table structure"""
    try:
        with engine.connect() as connection:
            print("\n📋 Final users table structure:")
            result = connection.execute(text("DESCRIBE users"))
            for row in result:
                null_str = "NULL" if row[2] == "YES" else "NOT NULL"
                key_str = f" ({row[3]})" if row[3] else ""
                default_str = f" DEFAULT {row[4]}" if row[4] else ""
                print(f"  - {row[0]}: {row[1]} {null_str}{key_str}{default_str}")
    except Exception as e:
        print(f"❌ ERROR: Could not show table structure: {e}")

if __name__ == "__main__":
    print("🔧 Fixing email column constraints...")
    print("-" * 50)
    
    success = fix_email_constraints()
    
    if success:
        show_final_structure()
        print("\n✅ All constraints fixed! FastAPI should work now.")
    else:
        print("\n❌ Constraint fix failed! Check errors above.")
        sys.exit(1)