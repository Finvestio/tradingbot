# FastAPI Server - Correct Startup Instructions

## ✅ **Problem Identified**
You're using the system conda environment instead of your project's virtual environment. The `pymysql` package is installed in the virtual environment but not in the conda environment.

## 🔧 **Solution - Use Virtual Environment**

### **Method 1: Activate Virtual Environment First**
```powershell
# Navigate to project directory
cd C:\Users\yassi\Desktop\trading_bot

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Verify you're using the right Python
python -c "import sys; print('Python:', sys.executable)"
# Should show: C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe

# Install uvicorn if needed
pip install uvicorn fastapi pymysql python-dotenv

# Start the server
uvicorn app.api:app --reload --port 8081
```

### **Method 2: Use Full Path (Recommended)**
```powershell
# Navigate to project directory
cd C:\Users\yassi\Desktop\trading_bot

# Run uvicorn directly from virtual environment
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe -m uvicorn app.api:app --reload --port 8081
```

### **Method 3: Use the Python Script**
```powershell
# Navigate to project directory
cd C:\Users\yassi\Desktop\trading_bot

# Run the custom server script
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe run_server.py
```

## 📋 **Verification Steps**

### **1. Check Environment Setup**
```powershell
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe -c "import pymysql; print('pymysql available')"
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe -c "import fastapi; print('fastapi available')"
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe -c "from app.api import app; print('API imports successfully')"
```

### **2. Test Database Connection**
```powershell
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe -c "from app.database import SessionLocal; from app.models import MarketData; s = SessionLocal(); print('DB records:', s.query(MarketData).count()); s.close()"
```

## 🚀 **Expected Output**
When the server starts correctly, you should see:
```
INFO:     Will watch for changes in these directories: ['C:\\Users\\yassi\\Desktop\\trading_bot']
INFO:     Uvicorn running on http://127.0.0.1:8081 (Press CTRL+C to quit)
INFO:     Started reloader process [XXXX] using StatReload
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## 🔧 **Why This Happens**
- Your system has multiple Python environments (conda base + virtual environment)
- When you run `uvicorn` without specifying the full path, it uses the system PATH which points to conda
- The `pymysql` package is only installed in the virtual environment
- Solution: Always use the virtual environment's Python executable

## ✅ **Quick Fix Commands**
```powershell
cd C:\Users\yassi\Desktop\trading_bot
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe -m pip install uvicorn pymysql fastapi python-dotenv
C:\Users\yassi\Desktop\trading_bot\.venv\Scripts\python.exe -m uvicorn app.api:app --reload --port 8081
```

**This should resolve the import error and start your server successfully!** 🎉