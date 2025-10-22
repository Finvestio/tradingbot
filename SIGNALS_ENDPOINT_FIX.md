# Fixed /api/signals Endpoint - Backend

## Issue Identified
The original `/api/signals` endpoint was failing with a `KeyError: 'Date'` because it was trying to access a 'Date' column that didn't exist as a regular column in the DataFrame - it was actually the index.

## Root Cause Analysis
1. **DataFrame Structure**: The `load_market_data(symbol)` function returns a DataFrame where:
   - **Index**: Datetime objects (the dates)
   - **Columns**: Only `["Close"]` initially
2. **Original Problem**: The code tried to access `result_df["Date"]` after selecting columns, but "Date" wasn't a column - it was the index.

## Fix Applied

### Before (Broken):
```python
# This failed because "Date" wasn't a column yet
result_df = df[["Close", "SMA_fast", "SMA_slow", "Signal"]].tail(20).reset_index()
result_df["Date"] = result_df["Date"].dt.strftime("%Y-%m-%d")  # KeyError!
```

### After (Fixed):
```python
# Proper sequence: select columns, get last 20, reset index, then rename columns
result_df = df[["Close", "SMA_fast", "SMA_slow", "Signal"]].tail(20).reset_index()

# After reset_index(), the date becomes the first column (position 0)
result_df.columns = ["Date", "Close", "SMA_fast", "SMA_slow", "Signal"]

# Now we can safely format the Date column
result_df["Date"] = result_df["Date"].dt.strftime("%Y-%m-%d")
```

## Key Changes Made

### 1. **Proper Column Handling**
- Used `reset_index()` to convert datetime index to a regular column
- Explicitly set column names after reset to ensure "Date" is properly named
- Followed the same pattern as the working `/api/run_strategy` endpoint

### 2. **Consistent Data Processing**
- Same SMA calculation logic as `/api/run_strategy`
- Same signal generation logic (1, -1, 0)
- Same date formatting pattern ("%Y-%m-%d")

### 3. **Error Prevention**
- Removed ambiguous date column access
- Clear column ordering: Date, Close, SMA_fast, SMA_slow, Signal
- Proper DataFrame manipulation sequence

## Endpoint Specification

### URL
```
GET /api/signals?symbol=AAPL&fast=10&slow=20
```

### Response Format
```json
{
  "symbol": "AAPL",
  "fast": 10,
  "slow": 20,
  "signals": [
    {
      "Date": "2025-10-22",
      "Close": 150.25,
      "SMA_fast": 149.75,
      "SMA_slow": 148.50,
      "Signal": 1
    }
    // ... 19 more records (last 20 total)
  ]
}
```

### Signal Values
- **1**: BUY signal (Fast SMA > Slow SMA)
- **-1**: SELL signal (Fast SMA < Slow SMA)
- **0**: HOLD signal (Fast SMA = Slow SMA)

## Testing

### Validation Steps
1. ✅ **Module Import**: `python -c "import app.api"` - Success
2. ✅ **Syntax Check**: No Python syntax errors
3. ✅ **Logic Consistency**: Matches `/api/run_strategy` pattern
4. 🧪 **Runtime Test**: Use `test_signals_endpoint.py` script

### Test Script Usage
```bash
# Start backend first
python -m uvicorn app.api:app --host 0.0.0.0 --port 8081 --reload

# Then run test (in separate terminal)
python test_signals_endpoint.py
```

## Integration Notes

### Frontend Compatibility
- The Angular frontend `getSignals()` method will now receive properly formatted data
- All expected columns (Date, Close, SMA_fast, SMA_slow, Signal) are present
- Data structure matches what the frontend table expects

### Error Handling
- Maintains existing error handling for invalid symbols
- Proper HTTP status codes (400 for bad requests)
- Clear error messages for debugging

### Performance
- Returns last 20 rows only (not full dataset)
- Efficient DataFrame operations
- Consistent with existing endpoint patterns

The `/api/signals` endpoint is now fixed and should work correctly with the Angular frontend to display your trading indicators!