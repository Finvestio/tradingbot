#!/usr/bin/env python3
"""
Simple test to verify all imports work correctly
"""
import sys
import os

# Add the project directory to Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

def test_imports():
    print("🧪 Testing imports...")
    
    try:
        print("  Testing app.data.loader...")
        from app.data.loader import load_market_data
        print("  ✅ app.data.loader imported successfully")
    except ImportError as e:
        print(f"  ❌ app.data.loader failed: {e}")
    
    try:
        print("  Testing app.backtest.metrics...")
        from app.backtest.metrics import compute_equity_curve, compute_metrics
        print("  ✅ app.backtest.metrics imported successfully")
    except ImportError as e:
        print(f"  ❌ app.backtest.metrics failed: {e}")
    
    try:
        print("  Testing app.database...")
        from app.database import get_db
        print("  ✅ app.database imported successfully")
    except ImportError as e:
        print(f"  ❌ app.database failed: {e}")
    
    try:
        print("  Testing app.db (MySQL functions)...")
        from app.db import (update_user_wallet, get_user_wallet, 
                           update_portfolio, record_order, get_user_portfolio, 
                           get_user_orders, init_database)
        print("  ✅ app.db imported successfully")
    except ImportError as e:
        print(f"  ❌ app.db failed: {e}")
    
    try:
        print("  Testing app.api...")
        from app.api import app
        print("  ✅ app.api imported successfully")
        print(f"  📍 API app available: {app is not None}")
    except ImportError as e:
        print(f"  ❌ app.api failed: {e}")
    except Exception as e:
        print(f"  ❌ app.api error: {e}")
    
    print("\n🎉 Import test completed!")

if __name__ == "__main__":
    test_imports()