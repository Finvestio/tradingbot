#!/usr/bin/env python3
"""
Test script for the /api/signals endpoint
"""

import requests
import json

def test_signals_endpoint():
    """Test the /api/signals endpoint"""
    base_url = "http://localhost:8081"
    
    # Test parameters
    test_cases = [
        {"symbol": "AAPL", "fast": 10, "slow": 20},
        {"symbol": "TSLA", "fast": 5, "slow": 15},
    ]
    
    for test_case in test_cases:
        print(f"\n🧪 Testing /api/signals with params: {test_case}")
        
        try:
            # Make request to signals endpoint
            response = requests.get(
                f"{base_url}/api/signals",
                params=test_case,
                timeout=30
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success! Got {len(data['signals'])} signals")
                
                # Print first few signals for verification
                print("\nSample signals:")
                for i, signal in enumerate(data['signals'][:3]):
                    print(f"  {i+1}. Date: {signal['Date']}, Close: {signal['Close']:.2f}, "
                          f"Signal: {signal['Signal']}, Fast SMA: {signal.get('SMA_fast', 'N/A')}")
                
                # Verify required fields
                required_fields = ["Date", "Close", "SMA_fast", "SMA_slow", "Signal"]
                first_signal = data['signals'][0] if data['signals'] else {}
                missing_fields = [field for field in required_fields if field not in first_signal]
                
                if missing_fields:
                    print(f"❌ Missing fields: {missing_fields}")
                else:
                    print("✅ All required fields present")
                    
            else:
                print(f"❌ Error: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    print("🚀 Testing /api/signals endpoint...")
    print("Make sure the backend server is running on http://localhost:8081")
    print("-" * 60)
    
    test_signals_endpoint()
    
    print("\n" + "=" * 60)
    print("Test completed!")