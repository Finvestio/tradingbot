# 🚀 Enhanced Trading Bot - Complete Setup Guide

## Overview
Your trading bot has been fully upgraded with:
- ✅ **MySQL Database Integration** (via XAMPP)
- ✅ **Order Management System** with wallet balances
- ✅ **Market Data Caching** from Alpha Vantage API
- ✅ **Enhanced Angular Frontend** with tabbed interface
- ✅ **Complete CRUD Operations** for users and orders

## Architecture
```
Frontend (Angular) ←→ Backend (FastAPI) ←→ MySQL Database
     Port 4200             Port 8081         Port 3306
```

## 📋 Prerequisites Setup

### 1. Database Setup (XAMPP)
- Start XAMPP Control Panel
- Start **Apache** and **MySQL** services
- Open phpMyAdmin: http://localhost/phpmyadmin
- The database `trading_bot` should exist with these tables:
  - `users` (id, username, email, wallet_balance, created_at)
  - `order_trades` (id, user_id, symbol, action, price, qty, total, created_at)
  - `market_data` (id, symbol, date, open, high, low, close, volume)

### 2. Environment Setup
- Python virtual environment: `C:\Users\yassi\Desktop\trading_bot\.venv`
- Node.js for Angular development
- All dependencies should be installed

## 🚀 Running the Application

### Step 1: Start the Backend (FastAPI)
```bash
cd C:\Users\yassi\Desktop\trading_bot
.\start_server.bat
```
**Backend will be available at:** http://localhost:8081
- API Documentation: http://localhost:8081/docs
- Order Management: http://localhost:8081/api/orders/
- Market Data: http://localhost:8081/api/market_data

### Step 2: Start the Frontend (Angular)
```bash
cd C:\Users\yassi\Desktop\trading_bot\trading-dashboard
npm start
```
**Frontend will be available at:** http://localhost:4200

## 🎯 Features Overview

### 1. 📊 Strategy & Analysis Tab
- Run SMA crossover strategies
- View performance metrics
- Analyze trading signals
- See equity curves

### 2. 💰 Order Management Tab
**User Management:**
- Create new users with initial wallet balance
- View all users and balances
- Switch between users

**Order Placement:**
- Place BUY/SELL orders
- Real-time wallet balance validation
- Order total calculation
- Insufficient funds protection

**Order History:**
- View user-specific orders
- See all system orders
- Real-time order tracking

### 3. 📈 Market Data (MySQL) Tab
- View cached market data from Alpha Vantage
- Smart caching (database first, API fallback)
- Sortable data display
- Price change indicators
- Volume formatting

### 4. 🔴 Live Charts Tab
- Real-time SMA chart visualization
- Interactive charting

## 🛠 API Endpoints

### Market Data
- `GET /api/market_data?symbol=AAPL` - Get cached market data

### Strategy
- `POST /api/run_strategy` - Run SMA strategy
- `GET /api/signals` - Get trading signals

### Order Management
- `POST /api/orders/place` - Place an order
- `GET /api/orders/` - Get all orders
- `GET /api/orders/user/{user_id}` - Get user orders
- `GET /api/orders/users/{user_id}` - Get user details
- `GET /api/orders/users` - Get all users
- `POST /api/orders/users` - Create new user

## 📝 Example Usage

### 1. Create a User via API
```bash
curl -X POST http://localhost:8081/api/orders/users \
  -H "Content-Type: application/json" \
  -d '{"username":"trader1","email":"trader@example.com","wallet_balance":100000}'
```

### 2. Place an Order
```bash
curl -X POST http://localhost:8081/api/orders/place \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"symbol":"AAPL","action":"BUY","price":190,"qty":5}'
```

### 3. Check User Balance
```bash
curl http://localhost:8081/api/orders/users/1
```

## 🔍 Testing the Integration

1. **Start both servers** (backend and frontend)
2. **Navigate to** http://localhost:4200
3. **Test Order Management:**
   - Go to "Order Management" tab
   - Create a user or select existing user
   - Place a BUY order (ensure sufficient balance)
   - Check order history
4. **Test Market Data:**
   - Go to "Market Data (MySQL)" tab
   - Load data for AAPL (or run a strategy first)
   - View cached database results
5. **Test Strategy:**
   - Go to "Strategy & Analysis" tab
   - Run SMA strategy (this will cache market data)
   - View results and signals

## 💡 Key Features

### Smart Data Caching
- Market data is fetched from Alpha Vantage API
- Automatically cached in MySQL database
- Subsequent requests use cached data
- No redundant API calls

### Wallet Management
- Real-time balance tracking
- Order validation prevents overspending
- Balance updates with each order
- Support for multiple users

### Comprehensive UI
- Tabbed interface for different features
- Real-time data updates
- Error handling and validation
- Professional styling and UX

## 🔧 Troubleshooting

### Backend Issues
- Ensure XAMPP MySQL is running
- Check virtual environment activation
- Verify pymysql dependency
- Check database connection in .env file

### Frontend Issues
- Ensure `npm install` was run
- Check proxy configuration (proxy.conf.json)
- Verify backend is running on port 8081
- Check browser console for errors

### Database Issues
- Confirm database `trading_bot` exists
- Check table creation (run init_db.py if needed)
- Verify MySQL credentials in .env

## 🎉 Success Indicators
- Backend shows: "Uvicorn running on http://127.0.0.1:8081"
- Frontend shows: "Local: http://localhost:4200"
- No console errors in browser
- All tabs load successfully
- Orders can be placed and retrieved
- Market data displays correctly

Your trading bot is now a complete full-stack application ready for advanced trading operations!