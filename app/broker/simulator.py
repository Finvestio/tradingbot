import pandas as pd

class SimBroker:
    """Simple bar-based broker for backtesting or simulation."""

    def __init__(self, cash: float = 100_000, fee_bps: float = 1.0):
        self.initial_cash = cash
        self.cash = cash
        self.position = 0           # +qty long, −qty short
        self.avg_price = 0.0
        self.equity = cash
        self.fee_bps = fee_bps / 10_000
        self.trades = []            # list of dicts

    def trade(self, price: float, signal: int, qty: int = 10):
        """Execute trade given signal (+1 buy, −1 sell, 0 hold)."""
        if signal == 0:
            return

        fee = price * qty * self.fee_bps
        cost = price * qty + fee if signal == 1 else -price * qty + fee

        # Update cash and position
        self.cash -= cost
        self.position += signal * qty
        self.avg_price = price if self.position != 0 else 0.0

        self.trades.append(
            {"price": price, "signal": signal, "qty": qty, "fee": fee}
        )

    def update_equity(self, current_price: float):
        """Revalue total equity based on last price."""
        self.equity = self.cash + self.position * current_price
        return self.equity

    def summary(self) -> dict:
        realized_pnl = sum(
            -t["fee"] for t in self.trades
        )  # simplified fee loss only
        return {
            "cash": round(self.cash, 2),
            "position": self.position,
            "avg_price": round(self.avg_price, 2),
            "equity": round(self.equity, 2),
            "trades": len(self.trades),
            "realized_pnl": round(realized_pnl, 2),
        }
