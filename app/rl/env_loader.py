
import pandas as pd, mysql.connector
from app.rl.features import make_features, state_from_row

DB_CFG = dict(host="localhost", user="root", password="", database="trading_bot")

def load_bars_from_db(symbol: str, asset_type: str, start=None, end=None) -> pd.DataFrame:
    cnx = mysql.connector.connect(**DB_CFG)
    cur = cnx.cursor(dictionary=True)
    query = """
        SELECT ts, open, high, low, close, volume
        FROM market_bars
        WHERE symbol=%s AND asset_type=%s
        ORDER BY ts ASC
    """
    cur.execute(query, (symbol, asset_type))
    rows = cur.fetchall()
    cur.close(); cnx.close()
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"No bars found for {asset_type}:{symbol}")
    df.rename(columns=str.lower, inplace=True)
    return make_features(df)

def example_state(symbol="AAPL", asset_type="stock", window=30):
    df = load_bars_from_db(symbol, asset_type)
    idx = len(df)-1
    s = state_from_row(df, idx, window, position=0, cash_ratio=1.0)
    print("State shape:", s.shape)
    return s
