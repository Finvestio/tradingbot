#!/usr/bin/env python3
"""
Test script for the trading bot API endpoints
"""
import requests
import json
import time

BASE_URL = "http://localhost:8081/api"

def test_bot_endpoints():
    print("🧪 Testing Trading Bot API Endpoints")
    print("=" * 50)
    
    # Test data
    test_payload = {
        "symbol": "AAPL",
        "asset_type": "stock", 
        "user_id": 1
    }
    
    try:
        # Test 1: Check bot status (should be stopped initially)
        print("\n1️⃣ Testing bot status endpoint...")
        response = requests.get(f"{BASE_URL}/bot_status/{test_payload['user_id']}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test 2: Start the bot
        print("\n2️⃣ Testing start bot endpoint...")
        response = requests.post(f"{BASE_URL}/start_bot", json=test_payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test 3: Check bot status (should be running now)
        print("\n3️⃣ Testing bot status after starting...")
        time.sleep(2)  # Wait a moment
        response = requests.get(f"{BASE_URL}/bot_status/{test_payload['user_id']}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test 4: Try to start bot again (should return already running)
        print("\n4️⃣ Testing start bot when already running...")
        response = requests.post(f"{BASE_URL}/start_bot", json=test_payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test 5: Stop the bot
        print("\n5️⃣ Testing stop bot endpoint...")
        stop_payload = {"user_id": test_payload["user_id"]}
        response = requests.post(f"{BASE_URL}/stop_bot", json=stop_payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test 6: Check bot status (should be stopped now)
        print("\n6️⃣ Testing bot status after stopping...")
        time.sleep(1)  # Wait a moment
        response = requests.get(f"{BASE_URL}/bot_status/{test_payload['user_id']}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test 7: Try to stop bot again (should return not running)
        print("\n7️⃣ Testing stop bot when not running...")
        response = requests.post(f"{BASE_URL}/stop_bot", json=stop_payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        print("\n✅ All tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to the API server.")
        print("Make sure the FastAPI server is running on localhost:8081")
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")

if __name__ == "__main__":
    test_bot_endpoints()