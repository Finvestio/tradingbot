#!/usr/bin/env python3
"""
Start both the FastAPI backend and Angular frontend for the trading bot application.
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path

def start_backend():
    """Start the FastAPI backend server."""
    print("🚀 Starting FastAPI backend on http://localhost:8081...")
    backend_process = subprocess.Popen([
        sys.executable, "-m", "uvicorn", 
        "app.api:app", 
        "--host", "0.0.0.0", 
        "--port", "8081",
        "--reload"
    ], cwd=Path(__file__).parent)
    return backend_process

def start_frontend():
    """Start the Angular frontend development server."""
    print("🚀 Starting Angular frontend on http://localhost:4200...")
    frontend_dir = Path(__file__).parent / "trading-dashboard"
    
    # Check if node_modules exists
    if not (frontend_dir / "node_modules").exists():
        print("📦 Installing npm dependencies...")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
    
    frontend_process = subprocess.Popen([
        "npm", "start"
    ], cwd=frontend_dir)
    return frontend_process

def main():
    """Main function to start both servers."""
    print("🎯 Starting Trading Bot Full Application")
    print("=" * 50)
    
    # Start backend
    backend_process = start_backend()
    time.sleep(3)  # Give backend time to start
    
    # Start frontend
    frontend_process = start_frontend()
    
    print("\n✅ Both servers started successfully!")
    print("📊 Backend API: http://localhost:8081")
    print("🌐 Frontend UI: http://localhost:4200")
    print("\nPress Ctrl+C to stop both servers...")
    
    try:
        # Wait for processes
        while True:
            time.sleep(1)
            # Check if processes are still running
            if backend_process.poll() is not None:
                print("❌ Backend process terminated")
                break
            if frontend_process.poll() is not None:
                print("❌ Frontend process terminated")
                break
    except KeyboardInterrupt:
        print("\n🛑 Shutting down servers...")
        
        # Terminate processes
        try:
            backend_process.terminate()
            frontend_process.terminate()
            
            # Wait a bit for graceful shutdown
            time.sleep(2)
            
            # Force kill if still running
            if backend_process.poll() is None:
                backend_process.kill()
            if frontend_process.poll() is None:
                frontend_process.kill()
                
            print("✅ Servers stopped successfully")
        except Exception as e:
            print(f"⚠️ Error stopping servers: {e}")

if __name__ == "__main__":
    main()