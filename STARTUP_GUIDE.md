# 🚀 Trading Bot - Complete Startup Guide

## Code Synchronization Status ✅
- ✅ Python User model updated with `email` and `created_at` fields
- ✅ Angular TypeScript interfaces match Python models exactly  
- ✅ API endpoints synchronized between backend and frontend
- ✅ Angular proxy configuration fixed for API routing
- ✅ Database initialization script updated for new tables

## Prerequisites
1. **XAMPP MySQL Running**: Ensure MySQL service is active
2. **Virtual Environment**: Python environment should be activated
3. **Node.js**: Ensure npm is available for Angular

## Startup Sequence

### Step 1: Initialize Database (First Time Only)
```bash
cd C:\Users\yassi\Desktop\trading_bot
.\.venv\Scripts\python.exe scripts\init_db.py
```

### Step 2: Start FastAPI Backend
```bash
# Terminal 1 - Backend
cd C:\Users\yassi\Desktop\trading_bot
.\.venv\Scripts\python.exe -m uvicorn app.api:app --reload --port 8081
```

Wait for: `INFO: Application startup complete.`

### Step 3: Start Angular Frontend  
```bash
# Terminal 2 - Frontend (NEW TERMINAL)
cd C:\Users\yassi\Desktop\trading_bot\trading-dashboard
npm start
```

Wait for: `✔ Compiled successfully.`

## Access URLs
- **Frontend**: http://localhost:4200
- **Backend API Docs**: http://localhost:8081/docs
- **Backend Health**: http://localhost:8081

## API Endpoints Available

### Strategy & Market Data
- `POST /api/run_strategy` - Run trading strategy
- `GET /api/signals` - Get trading signals  
- `GET /api/market_data` - Get cached market data

### User Management
- `GET /api/orders/users` - Get all users
- `POST /api/orders/users` - Create new user
- `GET /api/orders/users/{user_id}` - Get specific user
- `GET /api/orders/user/{user_id}/balance` - Get user balance
- `GET /api/orders/user/{user_id}/trades` - Get user trades

### Order Management  
- `POST /api/orders/place` - Place buy/sell order
- `GET /api/orders/` - Get all orders
- `GET /api/orders/user/{user_id}` - Get user orders

## Database Tables
- `market_data` - Cached Alpha Vantage data
- `signals` - Trading signals  
- `trades` - Strategy backtest trades
- `episodes` - RL training episodes
- `training_runs` - RL model training runs
- `models` - Trained RL models
- `users` - User accounts with wallets
- `order_trades` - User trading orders

## Proxy Configuration
Angular development server will automatically proxy all `/api/*` requests to `http://127.0.0.1:8081` thanks to:

**proxy.conf.json:**
```json
{
  "/api/*": {
    "target": "http://127.0.0.1:8081", 
    "secure": false,
    "changeOrigin": true,
    "logLevel": "debug"
  }
}
```

## Troubleshooting

### "Cannot match any routes. URL Segment: 'api/orders/...'"
This happens when Angular tries to route API calls internally. **Solution:**
1. Stop Angular server (Ctrl+C)
2. Restart with: `npm start` (which includes `--proxy-config proxy.conf.json`)

### Backend Import Errors
If you see import errors in backend, run:
```bash
cd C:\Users\yassi\Desktop\trading_bot
.\.venv\Scripts\python.exe -c "from app.api import app; print('API imported successfully!')"
```

### Database Connection Issues  
1. Ensure XAMPP MySQL is running
2. Check database exists: `trading_bot`
3. Re-run: `python scripts\init_db.py`

## Default Test Data
Create a test user via Angular UI:
- Username: `testuser`
- Email: `test@example.com`  
- Initial Balance: `$100,000`

## Development Notes
- Backend runs in reload mode - auto-restarts on Python file changes
- Frontend runs in watch mode - auto-recompiles on TypeScript changes
- All API calls from Angular are automatically proxied to backend
- CORS is configured to allow frontend → backend communication