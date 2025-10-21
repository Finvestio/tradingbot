import pandas as pd
import numpy as np



def compute_equity_curve(price_series: pd.Series, signals: pd.Series, initial_cash: float = 100_000, qty: int = 10) -> pd.Series:
    """Simulate portfolio value over time using price + signal series."""
    # ensure numeric
    price_series = pd.to_numeric(price_series, errors="coerce").fillna(method="ffill")

    cash = initial_cash
    position = 0
    equity = []

    for price, signal in zip(price_series, signals):
        price = float(price)
        if signal == 1:
            cash -= price * qty
            position += qty
        elif signal == -1 and position >= qty:
            cash += price * qty
            position -= qty
        total_value = cash + position * price
        equity.append(total_value)

    return pd.Series(equity, index=price_series.index)

def compute_metrics(equity_curve: pd.Series) -> dict:
    """Compute key portfolio metrics."""
    returns = equity_curve.pct_change().fillna(0)
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
    annualized_return = (1 + total_return) ** (252 / len(equity_curve)) - 1
    sharpe = np.sqrt(252) * returns.mean() / returns.std() if returns.std() > 0 else 0
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_drawdown = drawdown.min()
    return {
        "Total_Return_%": round(total_return * 100, 2),
        "Annualized_Return_%": round(annualized_return * 100, 2),
        "Sharpe_Ratio": round(sharpe, 2),
        "Max_Drawdown_%": round(max_drawdown * 100, 2),
    }
