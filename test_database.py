#!/usr/bin/env python3
"""
Test script to verify database connection and table creation
Run this script to test the MySQL database setup
"""

import sys
import os

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

try:
    from database import SessionLocal, init_database, engine
    from models import MarketData, Signal, Trade, Episode, TrainingRun, Model
    print("✅ Successfully imported database modules")
    
    # Initialize database and create tables
    print("🔄 Initializing database and creating tables...")
    init_database()
    print("✅ Database tables created successfully")
    
    # Test basic database connection
    print("🔄 Testing database connection...")
    session = SessionLocal()
    
    try:
        # Test MarketData table
        count = session.query(MarketData).count()
        print(f"✅ MarketData table accessible - Current count: {count}")
        
        # Test other tables
        signal_count = session.query(Signal).count()
        print(f"✅ Signal table accessible - Current count: {signal_count}")
        
        episode_count = session.query(Episode).count()
        print(f"✅ Episode table accessible - Current count: {episode_count}")
        
        trade_count = session.query(Trade).count()
        print(f"✅ Trade table accessible - Current count: {trade_count}")
        
        training_run_count = session.query(TrainingRun).count()
        print(f"✅ TrainingRun table accessible - Current count: {training_run_count}")
        
        model_count = session.query(Model).count()
        print(f"✅ Model table accessible - Current count: {model_count}")
        
        print("\n🎉 All database tests passed!")
        print("📊 Database Summary:")
        print(f"   - MarketData records: {count}")
        print(f"   - Signal records: {signal_count}")
        print(f"   - Episode records: {episode_count}")
        print(f"   - Trade records: {trade_count}")
        print(f"   - TrainingRun records: {training_run_count}")
        print(f"   - Model records: {model_count}")
        
    except Exception as e:
        print(f"❌ Database query error: {e}")
        sys.exit(1)
    finally:
        session.close()
        
    # Test inserting sample data
    print("\n🔄 Testing sample data insertion...")
    session = SessionLocal()
    try:
        from datetime import date
        
        # Check if sample data already exists
        existing = session.query(MarketData).filter_by(symbol="TEST").first()
        if not existing:
            # Insert sample market data
            sample_data = MarketData(
                symbol="TEST",
                date=date.today(),
                close=100.50,
                open=99.75,
                high=101.25,
                low=99.50,
                volume=1000000
            )
            session.add(sample_data)
            session.commit()
            print("✅ Sample MarketData record inserted successfully")
        else:
            print("✅ Sample data already exists")
            
        # Verify the insertion
        test_count = session.query(MarketData).filter_by(symbol="TEST").count()
        print(f"✅ TEST symbol records: {test_count}")
        
    except Exception as e:
        print(f"❌ Sample data insertion error: {e}")
        session.rollback()
    finally:
        session.close()

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you have installed the required dependencies:")
    print("pip install sqlalchemy pymysql python-dotenv")
    sys.exit(1)
    
except Exception as e:
    print(f"❌ Database connection error: {e}")
    print("\n🔧 Troubleshooting steps:")
    print("1. Make sure XAMPP MySQL is running")
    print("2. Create database 'trading_bot' in MySQL")
    print("3. Check database credentials in .env file")
    print("4. Verify MySQL is accessible on localhost:3306")
    sys.exit(1)