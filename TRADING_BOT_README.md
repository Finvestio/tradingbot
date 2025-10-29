# 🤖 Automated Trading Bot Documentation

## Overview

The Trading Bot implements an automated SMA (Simple Moving Average) crossover strategy that can execute trades every 30 seconds based on technical analysis. The bot integrates seamlessly with the Strategy & Analysis page of the trading dashboard.

## Features

- **Automated Trading**: Executes trades every 30 seconds using SMA crossover signals
- **Multi-Asset Support**: Works with stocks, crypto, and derivatives
- **Real-time Monitoring**: Live status updates and trade logging
- **User Management**: Each user can run their own bot instance
- **Safety Controls**: Easy start/stop functionality with status checking

## How It Works

### SMA Crossover Strategy

The bot uses a dual SMA strategy:
- **Fast SMA**: Default 10-period moving average
- **Slow SMA**: Default 20-period moving average

**Trading Signals:**
- **BUY**: When Fast SMA > Slow SMA (bullish crossover)
- **SELL**: When Fast SMA < Slow SMA (bearish crossover)
- **HOLD**: When no clear signal or insufficient funds/position

### Bot Behavior

1. **Data Fetching**: Retrieves latest market data from TwelveData API
2. **SMA Calculation**: Computes Fast and Slow SMAs
3. **Signal Generation**: Determines BUY/SELL/HOLD signals
4. **Trade Execution**: Executes 1 share/unit per signal (when conditions met)
5. **Wallet Management**: Tracks mock wallet balance and position size
6. **Logging**: Outputs all trades and decisions to console

## API Endpoints

### Start Bot
```http
POST /api/start_bot
```

**Request Body:**
```json
{
  "symbol": "AAPL",
  "asset_type": "stock", 
  "user_id": 1
}
```

**Response:**
```json
{
  "status": "bot_started",
  "symbol": "AAPL",
  "asset_type": "stock", 
  "user_id": 1,
  "message": "Automated trading bot started for user 1 on stock:AAPL"
}
```

### Stop Bot
```http
POST /api/stop_bot
```

**Request Body:**
```json
{
  "user_id": 1
}
```

**Response:**
```json
{
  "status": "bot_stopped",
  "user_id": 1,
  "message": "Trading bot stopped for user 1"
}
```

### Check Bot Status
```http
GET /api/bot_status/{user_id}
```

**Response:**
```json
{
  "user_id": 1,
  "is_running": true,
  "status": "running"
}
```

## Frontend Integration

### Angular Component

The bot controls are integrated into the Strategy & Analysis tab:

```typescript
// Bot properties
botStatus: string = '';
isBotRunning: boolean = false;

// Start bot method
async startBot() {
  const payload = {
    symbol: this.selectedSymbol,
    asset_type: this.selectedAssetType,
    user_id: this.selectedUser
  };
  // API call and status handling
}
```

### UI Components

- **Start Bot Button**: Initiates automated trading
- **Stop Bot Button**: Halts the trading bot
- **Status Display**: Shows current bot state and activity
- **Safety Features**: Buttons disable appropriately based on bot state

## Usage Instructions

1. **Select User**: Choose the user from the dropdown
2. **Choose Asset**: Select asset type (Stock/Crypto/Derivative) and symbol
3. **Configure SMAs**: Set Fast and Slow SMA periods (default: 10, 20)
4. **Start Bot**: Click "Start Bot" to begin automated trading
5. **Monitor**: Watch console logs for real-time trade activity
6. **Stop Bot**: Click "Stop Bot" to halt trading at any time

## Console Output Example

```
🤖 Bot started for user 1 trading stock:AAPL
💰 Initial wallet: $100,000.00
🟢 BUY 1 AAPL at $189.50
   💰 Wallet: $99,810.50 | Position: 1 shares
   📊 Fast SMA: $188.75 | Slow SMA: $187.20
⚪ HOLD AAPL at $190.25 | Wallet: $99,810.50 | Position: 1
   📊 Fast SMA: $189.10 | Slow SMA: $187.45
🔴 SELL 1 AAPL at $191.00
   💰 Wallet: $100,001.50 | Position: 0 shares
   📊 Fast SMA: $189.85 | Slow SMA: $188.90
🛑 Bot stopped for user 1
```

## Technical Implementation

### Backend Threading

- Uses Python `threading.Thread` for concurrent bot execution
- Each user gets their own bot thread
- Daemon threads for automatic cleanup on server shutdown
- Global `active_bots` dictionary tracks running instances

### Error Handling

- Market data fetch failures are logged and retried
- SMA calculation requires minimum data points
- Wallet/position validation before trade execution
- Graceful shutdown on stop command

### Safety Features

- One bot per user limitation
- Automatic cleanup on server restart
- Proper thread management and resource cleanup
- Input validation for all API endpoints

## Configuration Options

### Current Settings
- **Trade Frequency**: 30 seconds per cycle
- **Initial Wallet**: $100,000 (mock)
- **Position Size**: 1 share/unit per trade
- **Fast SMA**: 10 periods
- **Slow SMA**: 20 periods

### Future Enhancements
- Database wallet persistence
- Variable position sizing
- Multiple strategy algorithms
- Risk management rules
- Performance analytics
- Trade history logging

## Testing

Use the provided test script to validate API functionality:

```bash
python test_bot_api.py
```

The script tests all endpoints and provides comprehensive output for debugging.

## Troubleshooting

### Common Issues

1. **Bot Won't Start**: Check user selection and market data availability
2. **No Trades Executing**: Verify SMA calculations have sufficient data
3. **Console Spam**: Normal behavior - bot logs every 30-second cycle
4. **Bot Status Incorrect**: Refresh page or check API connectivity

### Debug Steps

1. Check FastAPI server logs for errors
2. Verify TwelveData API key and data access
3. Confirm user exists in database
4. Test API endpoints manually with test script

## Security Considerations

- **Rate Limiting**: Consider API rate limits for production use
- **User Authentication**: Implement proper user validation
- **Trade Limits**: Add maximum trade size and frequency limits
- **Data Validation**: Sanitize all user inputs and API responses