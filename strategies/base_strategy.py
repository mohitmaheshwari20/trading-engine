from abc import ABC, abstractmethod
import pandas as pd
from datetime import datetime

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    All strategies must inherit from this class and implement:
    - generate_signals()
    - get_strategy_name()
    - check_confirmation() (optional — only needed for multi-day confirmation strategies)
    
    Signal types:
        SIGNAL_BUY   =  1  : Execute buy immediately
        SIGNAL_SELL  = -1  : Execute sell immediately
        SIGNAL_HOLD  =  0  : No action
        SIGNAL_WATCH =  2  : Crossover detected — add to watchlist, confirm on Day 3
    """

    # Signal type constants — use these in all strategies
    SIGNAL_BUY   =  1
    SIGNAL_SELL  = -1
    SIGNAL_HOLD  =  0
    SIGNAL_WATCH =  2

    def __init__(self, config):
        self.config = config
        self.name = self.get_strategy_name()

        # Common parameters
        self.position_size_pct        = config.get('position_size_pct', 0.05)
        self.stop_loss_pct            = config.get('stop_loss_pct', 0.08)
        self.max_concurrent_positions = config.get('max_concurrent_positions', 5)

        # Filters
        self.min_price  = config.get('min_price', 50)
        self.max_price  = config.get('max_price', 5000)
        self.min_volume = config.get('min_volume', 100000)

    @abstractmethod
    def generate_signals(self, df):
        """
        Generate signals for a stock based on latest data.

        Returns DataFrame with columns:
            Signal          : SIGNAL_BUY / SIGNAL_SELL / SIGNAL_HOLD / SIGNAL_WATCH
            Signal_Strength : 0.0 to 1.0
            Signal_Reason   : Text explanation
        """
        pass

    @abstractmethod
    def get_strategy_name(self):
        """Return the strategy name string."""
        pass

    def check_confirmation(self, df, crossover_date, crossover_adx):
        """
        Check Day 3 confirmation conditions after a WATCH signal.

        Called by the engine exactly 3 trading days after a SIGNAL_WATCH
        was generated. Subclasses override this method to implement their
        own confirmation logic.

        Default implementation: always returns False (no confirmation).
        Strategies that use multi-day confirmation must override this.

        Args:
            df              : Full price DataFrame up to today
            crossover_date  : Date when SIGNAL_WATCH was generated
            crossover_adx   : ADX value on the crossover date

        Returns:
            bool: True if confirmation conditions are met, False otherwise
        """
        return False

    def apply_filters(self, df):
        """Apply basic price and volume filters."""
        if df.empty:
            return False
        latest = df.iloc[-1]
        if latest['Adj Close'] < self.min_price:
            return False
        if latest['Adj Close'] > self.max_price:
            return False
        if latest['Volume'] < self.min_volume:
            return False
        return True

    def calculate_position_size(self, current_price, portfolio_value):
        """Calculate number of shares to buy based on position size %."""
        position_value = portfolio_value * self.position_size_pct
        return int(position_value / current_price)

    def calculate_stop_loss(self, entry_price):
        """Calculate stop loss price."""
        return entry_price * (1 - self.stop_loss_pct)

    def format_signal_output(self, symbol, df, signal, signal_strength, reason):
        """Format signal output in a standardised way."""
        latest = df.iloc[-1]
        return {
            'symbol'         : symbol,
            'date'           : latest['Date'],
            'strategy'       : self.name,
            'signal'         : signal,
            'signal_strength': signal_strength,
            'price'          : latest['Adj Close'],
            'volume'         : latest['Volume'],
            'reason'         : reason,
            'stop_loss'      : self.calculate_stop_loss(latest['Adj Close']) if signal == self.SIGNAL_BUY else None
        }

    def validate_data(self, df):
        """Validate DataFrame has required columns and sufficient data."""
        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return False, f"Missing columns: {missing}"
        if len(df) < 200:
            return False, f"Insufficient data: {len(df)} rows (need at least 200)"
        return True, None
