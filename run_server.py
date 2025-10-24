#!/usr/bin/env python3
"""
Run the FastAPI server with the correct environment
"""

import uvicorn
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the app
from app.api import app

if __name__ == "__main__":
    print("Starting FastAPI server on http://127.0.0.1:8081")
    print("Make sure MySQL (XAMPP) is running...")
    
    uvicorn.run(
        "app.api:app",
        host="127.0.0.1",
        port=8081,
        reload=True,
        reload_dirs=["."]
    )