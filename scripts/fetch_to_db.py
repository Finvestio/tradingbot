
import os, sys, requests
import pandas as pd
from dotenv import load_dotenv
import mysql.connector
from datetime import datetime

load_dotenv()
TD_KEY = os.getenv("TWELVEDATA_API_KEY")
DB_CFG = dict(
    host="localhost",
    user="root",
    password="",
    database="trading_bot",
)

def fetch_twelvedata(symbol: str, asset_type: str, interval="1day", outputsize=500):
    # Twelve Data: for crypto use pairs like BTC/USD; for stocks just AAPL
    if asset_type == "crypto" and "/" not in symbol:
        symbol = f"{symbol}/USD"
    url = (
        "https://api.twelvedata.com/time_series"
        f"?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TD_KEY}"
    )
    r = requests.get(url, timeout=30)
    js = r.json()
    if "values" not in js:
        raise RuntimeError(js.get("message") or str(js)[:200])
    df = pd.DataFrame(js["values"])
    df["ts"] = pd.to_datetime(df["datetime"])
    df["open"] = pd.to_numeric(df.get("open"), errors="coerce")
    df["high"] = pd.to_numeric(df.get("high"), errors="coerce")
    df["low"]  = pd.to_numeric(df.get("low"),  errors="coerce")
    df["close"]= pd.to_numeric(df.get("close"),errors="coerce")
    df["volume"]=pd.to_numeric(df.get("volume"),errors="coerce")
    return df[["ts","open","high","low","close","volume"]].sort_values("ts")

def upsert_bars(df: pd.DataFrame, symbol: str, asset_type: str):
    df = df.fillna(0)  # Replace NaN with 0 or another safe default

    cnx = mysql.connector.connect(**DB_CFG)
    cur = cnx.cursor()
    sql = """
    INSERT INTO market_bars (asset_type, symbol, ts, open, high, low, close, volume)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE open=VALUES(open), high=VALUES(high),
        low=VALUES(low), close=VALUES(close), volume=VALUES(volume)
    """
    rows = [
        (
            asset_type,
            symbol,
            row.ts.to_pydatetime(),
            float(row.open) if pd.notna(row.open) else 0.0,
            float(row.high) if pd.notna(row.high) else 0.0,
            float(row.low) if pd.notna(row.low) else 0.0,
            float(row.close) if pd.notna(row.close) else 0.0,
            float(row.volume) if pd.notna(row.volume) else 0.0,
        )
        for _, row in df.iterrows()
    ]
    cur.executemany(sql, rows)
    cnx.commit()
    cur.close()
    cnx.close()
    return len(rows)