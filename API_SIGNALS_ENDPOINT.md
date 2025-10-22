# New API Endpoint: /api/signals

## Overview
Added a new GET endpoint `/api/signals` to the FastAPI application that provides trading signals based on Simple Moving Average (SMA) crossover strategy.

## Endpoint Details

### URL
```
GET /api/signals
```

### Parameters
- **symbol** (required): Stock symbol (e.g., "AAPL", "TSLA", "MSFT")
- **fast** (optional): Fast SMA window size (default: 10)
- **slow** (optional): Slow SMA window size (default: 20)

### Example Request
```
GET http://localhost:8081/api/signals?symbol=AAPL&fast=10&slow=20
```

### Response Format
```json
{
  "symbol": "AAPL",
  "fast": 10,
  "slow": 20,
  "signals": [
    {
      "Date": "2023-01-01",
      "Close": 150.25,
      "SMA_fast": 148.75,
      "SMA_slow": 149.50,
      "Signal": -1
    },
    {
      "Date": "2023-01-02",
      "Close": 151.00,
      "SMA_fast": 149.25,
      "SMA_slow": 149.75,
      "Signal": -1
    }
    // ... up to 20 most recent records
  ]
}
```

## Signal Logic

The endpoint calculates trading signals based on SMA crossover:

- **Signal = 1**: Buy signal (SMA_fast > SMA_slow)
- **Signal = -1**: Sell signal (SMA_fast < SMA_slow)  
- **Signal = 0**: No signal (SMA_fast = SMA_slow)

## Data Processing

1. **Load Market Data**: Uses `load_market_data(symbol)` to fetch historical price data
2. **Calculate SMAs**: 
   - `SMA_fast = Close.rolling(fast).mean()`
   - `SMA_slow = Close.rolling(slow).mean()`
3. **Generate Signals**: Compares fast and slow SMAs to determine buy/sell signals
4. **Format Output**: Returns last 20 rows with Date, Close, SMA_fast, SMA_slow, and Signal
5. **Date Formatting**: Dates formatted as "YYYY-MM-DD" strings

## Error Handling

- **400 Bad Request**: If symbol is missing or invalid
- **400 Bad Request**: If data loading fails (e.g., invalid symbol)

## Usage Examples

### Basic Request
```bash
curl "http://localhost:8081/api/signals?symbol=AAPL"
```

### Custom SMA Parameters
```bash
curl "http://localhost:8081/api/signals?symbol=TSLA&fast=5&slow=15"
```

### Frontend Integration
```typescript
// In Angular service
async getSignals(symbol: string, fast: number = 10, slow: number = 20) {
  const params = new HttpParams()
    .set('symbol', symbol)
    .set('fast', fast.toString())
    .set('slow', slow.toString());
  return await firstValueFrom(this.http.get<any>('/api/signals', { params }));
}
```

## Response Data Structure

Each signal record contains:
- **Date**: Trading date (string, YYYY-MM-DD format)
- **Close**: Closing price (number)
- **SMA_fast**: Fast moving average value (number)
- **SMA_slow**: Slow moving average value (number)
- **Signal**: Trading signal (-1, 0, or 1)

## Integration Notes

- **Compatible with existing endpoints**: Does not affect `/api/run_strategy`
- **Same data source**: Uses the same `load_market_data` function
- **Consistent CORS**: Inherits existing CORS configuration
- **RESTful design**: Follows GET pattern for data retrieval
- **Parameterized**: Flexible SMA window configuration

## Testing

The endpoint can be tested with:
1. **Backend validation**: API module loads successfully
2. **Manual testing**: Direct HTTP requests to the endpoint
3. **Frontend integration**: Angular proxy will route `/api/signals` requests
4. **Documentation**: Available at `http://localhost:8081/docs` when server runs