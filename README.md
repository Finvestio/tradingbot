# Trading Bot Dashboard - Full Stack Application

## Overview
This is a complete trading bot application with a **Python FastAPI backend** and an **Angular frontend**. The bot implements a Simple Moving Average (SMA) crossover strategy for automated trading simulation.

## Architecture
- **Backend**: FastAPI server running on port 8081
- **Frontend**: Angular 17+ application running on port 4200
- **Strategy**: SMA crossover trading algorithm
- **Data Source**: Yahoo Finance API via yfinance library

## Quick Start

### Prerequisites
- Python 3.7+ with pip
- Node.js 18+ with npm
- Angular CLI (`npm install -g @angular/cli`)

### Option 1: Use the Startup Scripts (Recommended)

**For Windows PowerShell:**
```powershell
.\start_full_app.ps1
```

**For Python script:**
```bash
python start_full_app.py
```

### Option 2: Manual Setup

1. **Start Backend** (Terminal 1):
```bash
cd trading_bot
pip install -r app/requirements.txt
python -m uvicorn app.api:app --host 0.0.0.0 --port 8081 --reload
```

2. **Start Frontend** (Terminal 2):
```bash
cd trading-dashboard
npm install
ng serve
```

## Application URLs
- **Frontend Dashboard**: http://localhost:4200
- **Backend API**: http://localhost:8081
- **API Documentation**: http://localhost:8081/docs

## Features

### Trading Dashboard
- **Real-time Controls**: Configure trading parameters (symbol, SMA periods)
- **Portfolio Monitoring**: View cash, position, and total equity
- **Performance Metrics**: Track returns, Sharpe ratio, and drawdown
- **Equity Tracking**: Monitor portfolio value over time

### Backend API Endpoints
- `POST /bot/start` - Start trading bot with parameters
- `GET /bot/state` - Get current portfolio and metrics
- `POST /bot/reset` - Reset bot session
- `GET /bot/equity` - Get equity curve data

### Trading Strategy
The bot uses a **Simple Moving Average Crossover** strategy:
- **Buy Signal**: When fast SMA crosses above slow SMA
- **Sell Signal**: When fast SMA crosses below slow SMA
- **Default Settings**: 10-day fast SMA, 20-day slow SMA

## Usage Instructions

1. **Open the Dashboard**: Navigate to http://localhost:4200
2. **Configure Parameters**:
   - Symbol: Stock ticker (e.g., AAPL, TSLA, MSFT)
   - Fast SMA: Short-term moving average period (default: 10)
   - Slow SMA: Long-term moving average period (default: 20)
3. **Start Trading**: Click "Start" to run the simulation
4. **Monitor Results**: View portfolio status and performance metrics
5. **Reset**: Click "Reset" to clear the session and start over

## Technical Details

### Backend Components
- **FastAPI**: RESTful API server with automatic documentation
- **Data Loader**: Yahoo Finance integration for market data
- **Strategy Engine**: SMA crossover signal generation
- **Broker Simulator**: Portfolio management and order execution
- **Metrics Calculator**: Performance analytics and risk metrics

### Frontend Components
- **Angular 17**: Modern standalone component architecture
- **HttpClient**: Type-safe API communication
- **Reactive Forms**: Real-time parameter updates
- **Responsive Design**: Clean, professional UI

### Key Dependencies
**Backend:**
- fastapi, uvicorn (API server)
- pandas, numpy (data processing)
- yfinance (market data)
- pandas-ta (technical analysis)

**Frontend:**
- @angular/core, @angular/common (Angular framework)
- @angular/common/http (HTTP client)
- @angular/forms (form handling)

## Development

### Backend Development
```bash
cd trading_bot
python -m uvicorn app.api:app --reload --host 0.0.0.0 --port 8081
```

### Frontend Development
```bash
cd trading-dashboard
ng serve --open
```

### Building for Production
```bash
cd trading-dashboard
ng build --configuration production
```

## API Examples

### Start a Trading Session
```bash
curl -X POST "http://localhost:8081/bot/start?symbol=AAPL&fast=10&slow=20&cash=100000"
```

### Get Current State
```bash
curl -X GET "http://localhost:8081/bot/state"
```

### Reset Bot
```bash
curl -X POST "http://localhost:8081/bot/reset"
```

## Troubleshooting

### Common Issues
1. **Port Already in Use**: Make sure ports 4200 and 8081 are available
2. **CORS Errors**: The backend is configured for localhost:4200
3. **Module Not Found**: Run `pip install -r app/requirements.txt`
4. **Angular Build Errors**: Run `npm install` in trading-dashboard folder

### Debug Mode
- Backend logs: Check console output of uvicorn server
- Frontend logs: Open browser developer tools (F12)

## Project Structure
```
trading_bot/
├── app/                    # Backend application
│   ├── api.py             # FastAPI endpoints
│   ├── strategy/          # Trading strategies
│   ├── broker/            # Portfolio simulation
│   ├── data/              # Data management
│   └── backtest/          # Performance metrics
├── trading-dashboard/      # Frontend application
│   ├── src/app/           # Angular components
│   │   ├── components/    # UI components
│   │   └── services/      # API services
│   └── dist/              # Built application
├── start_full_app.py      # Python startup script
└── start_full_app.ps1     # PowerShell startup script
```

## License
This project is for educational and demonstration purposes.