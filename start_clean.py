#!/usr/bin/env python3
"""
Clean startup script for the trading bot system
Starts the API server with minimal logging
"""
import subprocess
import sys
import os
import time

def start_api_server():
    """Start the FastAPI server cleanly"""
    print("🚀 Starting Trading Bot API Server")
    print("=" * 40)
    
    try:
        # Change to project directory
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
        # Start server
        print("Starting API on http://127.0.0.1:8081")
        print("API Documentation: http://127.0.0.1:8081/docs")
        print("Press Ctrl+C to stop")
        print("-" * 40)
        
        # Run uvicorn with clean output
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "app.api:app",
            "--host", "127.0.0.1",
            "--port", "8081",
            "--reload",
            "--log-level", "info"
        ])
        
    except KeyboardInterrupt:
        print("\n✅ Server stopped gracefully")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you're in the trading_bot directory")
        print("2. Check if virtual environment is activated")
        print("3. Install dependencies: pip install -r app/requirements.txt")

if __name__ == "__main__":
    start_api_server()