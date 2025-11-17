#!/usr/bin/env python3
"""
Test script to verify WebSocket frontend integration works correctly.
This sends a test trade proposal via WebSocket to see if the Angular frontend receives it.
"""

import asyncio
import json
import time
from app.api import active_connections, send_notification

async def test_websocket_frontend():
    """Test sending a WebSocket message to frontend."""
    
    print("🧪 Testing WebSocket Frontend Integration")
    print("=" * 50)
    
    # Simulate a trade proposal message
    test_proposal = {
        "type": "proposal",
        "user_id": 1,
        "symbol": "AAPL", 
        "asset_type": "stock",
        "action": 1,  # BUY
        "price": 150.75,
        "equity": 95234.50,
        "timestamp": time.time(),
        "proposal_id": f"test_proposal_{int(time.time())}"
    }
    
    print(f"📋 Test proposal created: {json.dumps(test_proposal, indent=2)}")
    
    # Check if user 1 is connected
    user_id = 1
    if user_id in active_connections:
        print(f"✅ User {user_id} WebSocket connection found!")
        
        try:
            ws = active_connections[user_id]
            message_json = json.dumps(test_proposal)
            await ws.send_text(message_json)
            print(f"📡 WebSocket message sent successfully!")
            print(f"📋 Sent: {message_json}")
            
        except Exception as e:
            print(f"❌ Failed to send WebSocket message: {e}")
            
    else:
        print(f"❌ No WebSocket connection found for user {user_id}")
        print(f"📋 Available connections: {list(active_connections.keys())}")
        print("\n🔧 TO FIX:")
        print("1. Make sure the backend server is running: python start_full_app.py")
        print("2. Make sure the frontend is running: cd trading-dashboard && ng serve")
        print("3. Open browser to http://localhost:4200 to connect WebSocket")
        print("4. Run this test again")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_websocket_frontend())