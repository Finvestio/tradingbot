
import numpy as np
import pandas as pd

def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add basic indicators."""
    df = df.copy()
    df["ret"] = df["close"].pct_change().fillna(0)
    df["sma10"] = df["close"].rolling(10).mean().fillna(method="bfill")
    df["sma20"] = df["close"].rolling(20).mean().fillna(method="bfill")
    df["rsi"] = 100 - 100/(1 + df["ret"].clip(-0.2,0.2).rolling(14).mean().fillna(0))
    return df.ffill().bfill()

def state_from_row(df: pd.DataFrame, idx: int, window: int,
                   position: int, cash_ratio: float) -> np.ndarray:
    """Build flat state vector."""
    slice_ = df.iloc[idx-window+1:idx+1][["ret","sma10","sma20","rsi","close"]].to_numpy()
    slice_[:, -1] = slice_[:, -1] / slice_[-1, -1]   # normalize price
    aug = np.array([position, cash_ratio], dtype=np.float32)
    return np.concatenate([slice_.flatten(), aug]).astype(np.float32)
