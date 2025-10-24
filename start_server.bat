@echo off
cd /d "C:\Users\yassi\Desktop\trading_bot"
call .venv\Scripts\activate.bat
python -m uvicorn app.api:app --reload --port 8081
pause