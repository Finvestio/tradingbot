#!/usr/bin/env python3
"""
Test script for enhanced trading bot with MySQL integration
Tests all new endpoints and database operations
"""
import requests
import json
import time

BASE_URL = "http://localhost:8081/api"

def test_mysql_endpoints():
    print("🧪 Testing Enhanced Trading Bot MySQL Integration")
    print("=" * 60)
    
    # Test user for all operations
    test_user_id = 1
    
    try:
        # Test 1: Check wallet balance
        print("\n1️⃣ Testing wallet balance endpoint...")
        response = requests.get(f"{BASE_URL}/wallet/{test_user_id}")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            wallet_data = response.json()
            print(f"Wallet Balance: ${wallet_data['wallet_balance']:,.2f}")
        else:
            print(f"Response: {response.json()}")
        
        # Test 2: Check portfolio
        print("\n2️⃣ Testing portfolio endpoint...")
        response = requests.get(f"{BASE_URL}/portfolio/{test_user_id}")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            portfolio_data = response.json()
            print(f"Holdings: {len(portfolio_data['holdings'])} positions")
            print(f"Total Value: ${portfolio_data['total_holdings_value']:,.2f}")
        else:
            print(f"Response: {response.json()}")
        
        # Test 3: Check order history
        print("\n3️⃣ Testing orders endpoint...")
        response = requests.get(f"{BASE_URL}/orders/{test_user_id}")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            orders_data = response.json()
            print(f"Total Orders: {orders_data['total_orders']}")
            if orders_data['total_orders'] > 0:
                latest_order = orders_data['orders'][0]
                print(f"Latest: {latest_order['side']} {latest_order['quantity']} {latest_order['symbol']} @ ${latest_order['price']}")
        else:
            print(f"Response: {response.json()}")
        
        # Test 4: Portfolio summary
        print("\n4️⃣ Testing portfolio summary endpoint...")
        response = requests.get(f"{BASE_URL}/portfolio_summary/{test_user_id}")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            summary = response.json()
            print(f"Wallet: ${summary['wallet_balance']:,.2f}")
            print(f"Holdings: ${summary['total_holdings_value']:,.2f}")
            print(f"Total Portfolio: ${summary['total_portfolio_value']:,.2f}")
            print(f"Positions: {summary['positions_count']}")
            print(f"Recent Orders: {len(summary['recent_orders'])}")
        else:
            print(f"Response: {response.json()}")
        
        # Test 5: Start bot (brief test)
        print("\n5️⃣ Testing enhanced bot start...")
        bot_payload = {
            "symbol": "AAPL",
            "asset_type": "stock", 
            "user_id": test_user_id
        }
        response = requests.post(f"{BASE_URL}/start_bot", json=bot_payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Wait a moment then check bot status
        time.sleep(2)
        response = requests.get(f"{BASE_URL}/bot_status/{test_user_id}")
        print(f"Bot Status: {response.json()}")
        
        # Test 6: Stop bot
        print("\n6️⃣ Testing bot stop...")
        stop_payload = {"user_id": test_user_id}
        response = requests.post(f"{BASE_URL}/stop_bot", json=stop_payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        print("\n✅ All MySQL integration tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to the API server.")
        print("Make sure the FastAPI server is running on localhost:8081")
        print("Command: uvicorn app.api:app --reload --port 8081")
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")

def test_notification_stream():
    """
    Test Server-Sent Events notification stream
    """
    print("\n🔔 Testing Notification Stream (Server-Sent Events)")
    print("-" * 50)
    
    try:
        import sseclient  # pip install sseclient-py
        
        test_user_id = 1
        url = f"{BASE_URL}/notifications/{test_user_id}"
        
        print(f"Connecting to: {url}")
        print("Listening for notifications (will timeout after 10 seconds)...")
        
        response = requests.get(url, stream=True, timeout=10)
        client = sseclient.SSEClient(response)
        
        notification_count = 0
        for event in client.events():
            print(f"📨 Notification: {event.data}")
            notification_count += 1
            if notification_count >= 3:  # Stop after 3 messages
                break
        
        print(f"✅ Received {notification_count} notifications")
        
    except ImportError:
        print("⚠️ Skipping SSE test (install sseclient-py to test)")
        print("Command: pip install sseclient-py")
    except requests.exceptions.Timeout:
        print("⏰ SSE test completed (connection timeout is normal)")
    except Exception as e:
        print(f"❌ SSE test error: {str(e)}")

if __name__ == "__main__":
    test_mysql_endpoints()
    test_notification_stream()
    
    print("\n🎉 Testing Complete!")
    print("\n📝 Next Steps:")
    print("1. Check the Angular frontend at http://localhost:4200")
    print("2. Go to Order Management → Portfolio to see real-time data")
    print("3. Start a trading bot and watch for toast notifications")
    print("4. Monitor console logs for trade activity")