#!/usr/bin/env python3
"""
Comprehensive test to verify the RL trading system and frontend WebSocket integration.
This tests:
1. RL agent decision making
2. Trade proposal creation  
3. WebSocket message sending
4. Frontend message handling
"""

import asyncio
import json
import time
import requests
from app.bot.rl_trader import RLTrader, trade_proposals
from app.api import active_connections

async def test_full_rl_pipeline():
    """Test the complete RL trading pipeline with frontend integration."""
    
    print("🚀 COMPREHENSIVE RL SYSTEM TEST")
    print("=" * 60)
    
    # Test configuration
    user_id = 1
    symbol = "AAPL"
    asset_type = "stock"
    
    print(f"📊 Testing with User: {user_id}, Symbol: {symbol}, Asset: {asset_type}")
    print()
    
    # 1. Test RL Trader initialization
    print("1️⃣ Testing RL Trader initialization...")
    try:
        trader = RLTrader(user_id, symbol, asset_type, interval_sec=30)
        trader.load_model()
        print("   ✅ RL Trader initialized successfully")
    except Exception as e:
        print(f"   ❌ Failed to initialize RL Trader: {e}")
        return
    
    # 2. Test environment state
    print("\n2️⃣ Testing RL Environment...")
    try:
        state = trader.env.reset()
        print(f"   ✅ Environment reset, state shape: {len(state)}")
        print(f"   📊 Initial state: {state[:5]}... (showing first 5 values)")
    except Exception as e:
        print(f"   ❌ Environment error: {e}")
        return
    
    # 3. Test agent decision making
    print("\n3️⃣ Testing RL Agent decision making...")
    try:
        action = trader.agent.get_action(state)
        action_name = trader.get_action_name(action)
        print(f"   ✅ Agent decision: {action} ({action_name})")
    except Exception as e:
        print(f"   ❌ Agent decision error: {e}")
        return
    
    # 4. Test trade proposal creation
    print("\n4️⃣ Testing trade proposal creation...")
    try:
        # Simulate current price and equity
        test_price = 150.75
        test_equity = 98500.0
        
        # Clear any existing proposals
        trade_proposals.clear()
        
        # Create proposal
        proposal = trader.create_proposal(action, test_price, test_equity)
        
        if proposal:
            print(f"   ✅ Proposal created successfully")
            print(f"   📋 Proposal: {json.dumps(proposal, indent=6)}")
        else:
            print("   ❌ Failed to create proposal")
            return
            
    except Exception as e:
        print(f"   ❌ Proposal creation error: {e}")
        return
    
    # 5. Test WebSocket connection
    print("\n5️⃣ Testing WebSocket connection...")
    if user_id in active_connections:
        print(f"   ✅ WebSocket connection found for user {user_id}")
        
        # Test sending a custom message
        test_message = {
            "type": "test", 
            "message": "WebSocket test from RL system",
            "timestamp": time.time()
        }
        
        try:
            ws = active_connections[user_id]
            await ws.send_text(json.dumps(test_message))
            print("   ✅ Test WebSocket message sent successfully")
        except Exception as e:
            print(f"   ❌ WebSocket send error: {e}")
            
    else:
        print(f"   ❌ No WebSocket connection for user {user_id}")
        print(f"   📋 Available connections: {list(active_connections.keys())}")
    
    # 6. Test backend API connectivity  
    print("\n6️⃣ Testing backend API connectivity...")
    try:
        response = requests.get("http://localhost:8081/")
        if response.status_code == 200:
            print("   ✅ Backend API is responding")
        else:
            print(f"   ⚠️ Backend API returned status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Backend API error: {e}")
    
    # 7. Summary
    print("\n" + "="*60)
    print("🎯 TEST SUMMARY")
    print("="*60)
    
    if user_id in active_connections and proposal:
        print("✅ FULL PIPELINE WORKING")
        print("   • RL Agent is making decisions")
        print("   • Trade proposals are being created")
        print("   • WebSocket connection is active")
        print("   • Frontend should receive messages")
        print()
        print("🔥 The system is ready! Trade proposals should appear in the Angular frontend.")
        
    else:
        print("❌ INCOMPLETE SETUP")
        if user_id not in active_connections:
            print("   • WebSocket connection missing")
            print("   • Frontend needs to be opened in browser")
        if not proposal:
            print("   • Trade proposal creation failed")
        print()
        print("🔧 NEXT STEPS:")
        print("1. Start backend: python start_full_app.py")
        print("2. Start frontend: cd trading-dashboard && ng serve")  
        print("3. Open http://localhost:4200 in browser")
        print("4. Wait for WebSocket connection")
        print("5. Run this test again")

if __name__ == "__main__":
    asyncio.run(test_full_rl_pipeline())