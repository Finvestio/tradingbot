#!/usr/bin/env python3
"""
Test script for database-cached market data loader
Tests the load_market_data function with MySQL integration
"""

import sys
import os

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.data.loader import load_market_data

def test_db_loader():
    """Test the database-cached market data loader"""
    try:
        print("🧪 Testing database-cached market data loader...")
        print("=" * 50)
        
        # Load AAPL data (will use cache if available, otherwise fetch from API)
        df = load_market_data("AAPL")
        
        print("\n📊 Data loaded successfully!")
        print("DataFrame Info:")
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"Index type: {type(df.index)}")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        
        print("\n📈 First 5 rows:")
        print(df.head())
        
        print("\n📈 Last 5 rows:")
        print(df.tail())
        
        print("\n✅ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_db_loader()
    if not success:
        sys.exit(1)