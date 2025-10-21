from abc import ABC, abstractmethod
import pandas as pd

class Strategy(ABC):
    """Abstract base for all strategies."""
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of -1, 0, or +1 signals."""
        pass