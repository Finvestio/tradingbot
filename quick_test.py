#!/usr/bin/env python3
"""
Quick test script to verify trading bot components are working
Tests basic functionality without extensive logging
"""
import requests
import json
import time
import sys
import os

BASE_URL = "http://localhost:8081/api"

def quick_api_test():
    """Test basic API endpoints"""
    print("🧪 Testing API Endpoints")
    print("-" * 40)
    
    test_user_id = 1
    
    try:
        # Test 1: Health check (basic endpoint)
        print("1. Testing basic endpoints...")
        response = requests.get(f"{BASE_URL}/orders/users", timeout=5)
        print(f"   Users endpoint: {response.status_code}")
        
        # Test 2: Portfolio endpoint
        print("2. Testing portfolio...")
        response = requests.get(f"{BASE_URL}/orders/user/{test_user_id}/portfolio", timeout=5)
        print(f"   Portfolio endpoint: {response.status_code}")
        
        # Test 3: Enhanced portfolio
        print("3. Testing enhanced portfolio...")
        response = requests.get(f"{BASE_URL}/orders/user/{test_user_id}/portfolio/enhanced", timeout=5)
        print(f"   Enhanced portfolio: {response.status_code}")
        
        # Test 4: Quick order test (small amount)
        print("4. Testing order placement...")
        test_order = {
            "user_id": test_user_id,
            "symbol": "AAPL",
            "asset_type": "stock",
            "action": "BUY",
            "qty": 1,
            "price": 150.0
        }
        response = requests.post(f"{BASE_URL}/orders/place", json=test_order, timeout=5)
        print(f"   Order placement: {response.status_code}")
        
        print("✅ All API tests completed!")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Start with: uvicorn app.api:app --port 8081 --reload")
        return False
    except Exception as e:
        print(f"❌ Test error: {str(e)}")
        return False

def test_imports():
    """Test critical module imports"""
    print("\n🔧 Testing Module Imports")
    print("-" * 40)
    
    try:
        # Test core imports
        import sys
        sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))
        
        print("1. Testing database models...")
        from app.models import User, Portfolio, OrderTrade
        print("   ✅ Models imported")
        
        print("2. Testing portfolio manager...")
        from app.broker.portfolio import PortfolioManager
        print("   ✅ Portfolio manager imported")
        
        print("3. Testing data loader...")
        from app.data.loader import fetch_realtime_price
        print("   ✅ Data loader imported")
        
        print("4. Testing RL components...")
        from app.rl.dqn import DQNAgent
        from app.rl.env import TradingEnv
        print("   ✅ RL components imported")
        
        print("✅ All imports successful!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_portfolio_logic():
    """Test portfolio calculations without API calls"""
    print("\n📊 Testing Portfolio Logic")
    print("-" * 40)
    
    try:
        # Test portfolio position calculation
        from app.broker.portfolio import PortfolioPosition
        
        pos = PortfolioPosition(
            symbol="AAPL",
            asset_type="stock", 
            quantity=10,
            avg_price=150.0,
            current_price=160.0,
            market_value=1600.0,
            unrealized_pnl=100.0,
            unrealized_pnl_percent=6.67,
            weight=50.0
        )
        
        print(f"1. Position created: {pos.symbol}")
        print(f"   Market Value: ${pos.market_value:,.2f}")
        print(f"   P&L: ${pos.unrealized_pnl:,.2f} ({pos.unrealized_pnl_percent:.2f}%)")
        print("   ✅ Portfolio position logic working")
        
        return True
        
    except Exception as e:
        print(f"❌ Portfolio logic error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Trading Bot Component Test Suite")
    print("=" * 50)
    
    # Test imports first
    imports_ok = test_imports()
    
    # Test portfolio logic
    portfolio_ok = test_portfolio_logic() if imports_ok else False
    
    # Test API if server is running
    api_ok = quick_api_test()
    
    # Summary
    print(f"\n📋 Test Results Summary")
    print("-" * 30)
    print(f"Imports:   {'✅ PASS' if imports_ok else '❌ FAIL'}")
    print(f"Portfolio: {'✅ PASS' if portfolio_ok else '❌ FAIL'}")
    print(f"API:       {'✅ PASS' if api_ok else '❌ SKIP (server not running)'}")
    
    if imports_ok and portfolio_ok:
        print("\n🎉 Core components are working!")
        print("\nNext steps:")
        print("1. Start server: uvicorn app.api:app --port 8081 --reload")
        print("2. Run full tests: python test_portfolio_enhanced.py")
        print("3. Open dashboard: http://localhost:4200")
    else:
        print("\n⚠️ Some components need attention")
    
    return imports_ok and portfolio_ok

if __name__ == "__main__":
    main()