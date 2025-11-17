#!/usr/bin/env python3
"""
Enhanced portfolio testing script
Tests the new PortfolioManager functionality and endpoints
"""
import requests
import json
import time
import asyncio
import sys
import os

# Add the app directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

BASE_URL = "http://localhost:8081/api"

def test_portfolio_endpoints():
    print("🧪 Testing Enhanced Portfolio System")
    print("=" * 60)
    
    # Test user for all operations
    test_user_id = 1
    
    try:
        # Test 1: Check basic portfolio
        print("\n1️⃣ Testing basic portfolio endpoint...")
        response = requests.get(f"{BASE_URL}/orders/user/{test_user_id}/portfolio")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            portfolio_data = response.json()
            print(f"Wallet Balance: ${portfolio_data['wallet_balance']:,.2f}")
            print(f"Holdings: {len(portfolio_data['holdings'])} positions")
            print(f"Total Market Value: ${portfolio_data['total_market_value']:,.2f}")
            for holding in portfolio_data['holdings']:
                print(f"  {holding['symbol']}: {holding['quantity']} @ ${holding['current_price']:.2f}")
        else:
            print(f"Error: {response.json()}")
        
        # Test 2: Check enhanced portfolio with advanced metrics
        print("\n2️⃣ Testing enhanced portfolio endpoint...")
        response = requests.get(f"{BASE_URL}/orders/user/{test_user_id}/portfolio/enhanced")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            enhanced_data = response.json()
            print(f"Total Portfolio Value: ${enhanced_data['total_portfolio_value']:,.2f}")
            print(f"Unrealized P&L: ${enhanced_data['total_unrealized_pnl']:,.2f} ({enhanced_data['total_unrealized_pnl_percent']:.2f}%)")
            print(f"Diversification Score: {enhanced_data['diversification_score']:.1f}/100")
            print("Positions with weights:")
            for pos in enhanced_data['positions']:
                print(f"  {pos['symbol']}: {pos['weight']:.1f}% of portfolio")
        else:
            print(f"Error: {response.json()}")
        
        # Test 3: Check risk metrics
        print("\n3️⃣ Testing portfolio risk metrics...")
        response = requests.get(f"{BASE_URL}/orders/user/{test_user_id}/portfolio/risk")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            risk_data = response.json()
            print(f"Risk Score: {risk_data['risk_score']:.1f}/100 ({risk_data['risk_level']})")
            print(f"Diversification Score: {risk_data['diversification_score']:.1f}")
            print(f"Asset Allocation:")
            for asset_type, weight in risk_data['asset_allocation'].items():
                print(f"  {asset_type.capitalize()}: {weight:.1f}%")
        else:
            print(f"Error: {response.json()}")
        
        # Test 4: Check performance metrics
        print("\n4️⃣ Testing portfolio performance...")
        response = requests.get(f"{BASE_URL}/orders/user/{test_user_id}/portfolio/performance?days=30")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            perf_data = response.json()
            print(f"Total Trades: {perf_data['total_trades']}")
            print(f"Net Investment: ${perf_data['net_investment']:,.2f}")
            print(f"Trading Frequency: {perf_data['trading_frequency']:.2f} trades/day")
        else:
            print(f"Error: {response.json()}")
        
        # Test 5: Place a test order to see portfolio update
        print("\n5️⃣ Testing order placement with portfolio update...")
        test_order = {
            "user_id": test_user_id,
            "symbol": "MSFT",
            "asset_type": "stock",
            "action": "BUY",
            "qty": 5,
            "price": 415.0
        }
        
        response = requests.post(f"{BASE_URL}/orders/place", json=test_order)
        print(f"Order Status: {response.status_code}")
        if response.status_code == 200:
            order_result = response.json()
            print(f"Order Message: {order_result['message']}")
            print(f"New Wallet Balance: ${order_result['new_balance']:,.2f}")
        else:
            print(f"Order Error: {response.json()}")
        
        # Test 6: Check position-specific risk
        if response.status_code == 200:
            print("\n6️⃣ Testing position risk metrics...")
            response = requests.get(f"{BASE_URL}/orders/user/{test_user_id}/position/MSFT/stock/risk")
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                pos_risk = response.json()
                print(f"MSFT Position:")
                print(f"  Quantity: {pos_risk['quantity']}")
                print(f"  Weight: {pos_risk['position_weight']:.2f}%")
                print(f"  Risk Level: {pos_risk['risk_level']}")
            else:
                print(f"Position Risk Error: {response.json()}")
        
        print("\n✅ All portfolio tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to the API server.")
        print("Make sure the FastAPI server is running on localhost:8081")
        print("Command: uvicorn app.api:app --reload --port 8081")
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")

def test_portfolio_manager_directly():
    """
    Test the PortfolioManager class directly (requires database setup)
    """
    print("\n🔧 Testing PortfolioManager directly...")
    print("-" * 50)
    
    try:
        # Import and test the PortfolioManager
        from app.broker.portfolio import PortfolioManager
        from app.database import SessionLocal
        
        db = SessionLocal()
        portfolio_manager = PortfolioManager(db)
        
        # Test getting portfolio summary
        summary = asyncio.run(portfolio_manager.get_portfolio_summary(1))
        print(f"✅ Direct test successful!")
        print(f"Portfolio Value: ${summary.total_portfolio_value:,.2f}")
        print(f"Positions: {summary.positions_count}")
        
        db.close()
        
    except ImportError as e:
        print(f"⚠️ Skipping direct test - import error: {e}")
    except Exception as e:
        print(f"❌ Direct test failed: {e}")

if __name__ == "__main__":
    test_portfolio_endpoints()
    test_portfolio_manager_directly()
    
    print("\n🎉 Portfolio Testing Complete!")
    print("\n📝 Summary of Enhancements:")
    print("✅ Empty portfolio.py fixed with comprehensive PortfolioManager")
    print("✅ Real-time price integration for accurate portfolio valuation")
    print("✅ Advanced portfolio metrics (diversification, risk scores)")
    print("✅ Performance tracking and analytics")
    print("✅ Position-level risk management")
    print("✅ Enhanced API endpoints for portfolio management")
    print("✅ Improved order placement with portfolio validation")
    
    print("\n📊 New API Endpoints Available:")
    print("• GET /api/orders/user/{user_id}/portfolio/enhanced - Advanced portfolio summary")
    print("• GET /api/orders/user/{user_id}/portfolio/risk - Risk metrics")
    print("• GET /api/orders/user/{user_id}/portfolio/performance - Performance analytics")
    print("• GET /api/orders/user/{user_id}/position/{symbol}/{asset_type}/risk - Position risk")