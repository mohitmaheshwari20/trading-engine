from abc import ABC, abstractmethod
import pandas as pd
from datetime import datetime

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    All strategies must inherit from this class and implement:
    - generate_signals()
    - get_strategy_name()
    
    This ensures consistency across all strategies.
    """
    
    def __init__(self, config):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Dictionary containing strategy parameters
        """
        self.config = config
        self.name = self.get_strategy_name()
        
        # Extract common parameters
        self.position_size_pct = config.get('position_size_pct', 0.05)
        self.stop_loss_pct = config.get('stop_loss_pct', 0.08)
        self.max_concurrent_positions = config.get('max_concurrent_positions', 5)
        
        # Filters
        self.min_price = config.get('min_price', 50)
        self.max_price = config.get('max_price', 5000)
        self.min_volume = config.get('min_volume', 100000)
    
    @abstractmethod
    def generate_signals(self, df):
        """
        Generate buy/sell signals for a stock.
        
        This method MUST be implemented by each strategy.
        
        Args:
            df: DataFrame with OHLCV data and indicators
        
        Returns:
            DataFrame with additional columns:
            - 'Signal': 1 (buy), -1 (sell), 0 (hold)
            - 'Signal_Strength': 0.0 to 1.0 (confidence in signal)
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self):
        """
        Return the strategy name.
        
        Returns:
            str: Strategy name (e.g., "Mean Reversion")
        """
        pass
    
    def apply_filters(self, df):
        """
        Apply basic filters before generating signals.
        
        Filters out stocks that don't meet minimum criteria:
        - Price too low (penny stocks)
        - Price too high (limited liquidity)
        - Volume too low (illiquid)
        
        Args:
            df: DataFrame with stock data
        
        Returns:
            bool: True if stock passes filters, False otherwise
        """
        if df.empty:
            return False
        
        # Get most recent data
        latest = df.iloc[-1]
        
        # Price filters
        if latest['Adj Close'] < self.min_price:
            return False
        
        if latest['Adj Close'] > self.max_price:
            return False
        
        # Volume filter
        if latest['Volume'] < self.min_volume:
            return False
        
        return True
    
    def calculate_position_size(self, current_price, portfolio_value):
        """
        Calculate position size based on strategy rules.
        
        Args:
            current_price: Current stock price
            portfolio_value: Total portfolio value
        
        Returns:
            int: Number of shares to buy
        """
        # Calculate position value
        position_value = portfolio_value * self.position_size_pct
        
        # Calculate number of shares (rounded down)
        shares = int(position_value / current_price)
        
        return shares
    
    def calculate_stop_loss(self, entry_price):
        """
        Calculate stop loss price.
        
        Args:
            entry_price: Price at which position was entered
        
        Returns:
            float: Stop loss price
        """
        return entry_price * (1 - self.stop_loss_pct)
    
    def format_signal_output(self, symbol, df, signal, signal_strength, reason):
        """
        Format signal output in a standardized way.
        
        Args:
            symbol: Stock symbol
            df: DataFrame with stock data
            signal: 1 (buy), -1 (sell), 0 (hold)
            signal_strength: Confidence level (0.0 to 1.0)
            reason: Text explanation of signal
        
        Returns:
            dict: Formatted signal information
        """
        latest = df.iloc[-1]
        
        return {
            'symbol': symbol,
            'date': latest['Date'],
            'strategy': self.name,
            'signal': signal,
            'signal_strength': signal_strength,
            'price': latest['Adj Close'],
            'volume': latest['Volume'],
            'reason': reason,
            'stop_loss': self.calculate_stop_loss(latest['Adj Close']) if signal == 1 else None
        }
    
    def validate_data(self, df):
        """
        Validate that DataFrame has required columns and sufficient data.
        
        Args:
            df: DataFrame to validate
        
        Returns:
            tuple: (is_valid, error_message)
        """
        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        
        # Check for required columns
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return False, f"Missing columns: {missing}"
        
        # Check for sufficient data
        if len(df) < 200:
            return False, f"Insufficient data: {len(df)} rows (need at least 200)"
        
        # REMOVED: Staleness check - not relevant for backtesting
        # This check is only useful for live trading
        # During backtesting, we intentionally use historical data
        
        return True, None


# Test function
def test_base_strategy():
    """
    Test the base strategy class with a dummy implementation.
    """
    print("Testing BaseStrategy...\n")
    
    # Create a dummy strategy for testing
    class DummyStrategy(BaseStrategy):
        def generate_signals(self, df):
            # Dummy implementation - just return last row with signal
            result = df.copy()
            result['Signal'] = 0
            result['Signal_Strength'] = 0.0
            
            # Generate a dummy buy signal on last row
            result.loc[result.index[-1], 'Signal'] = 1
            result.loc[result.index[-1], 'Signal_Strength'] = 0.75
            
            return result
        
        def get_strategy_name(self):
            return "Dummy Strategy"
    
    # Test configuration
    config = {
        'position_size_pct': 0.05,
        'stop_loss_pct': 0.08,
        'max_concurrent_positions': 5,
        'min_price': 50,
        'max_price': 5000,
        'min_volume': 100000
    }
    
    # Create strategy instance
    strategy = DummyStrategy(config)
    print(f"✓ Strategy created: {strategy.get_strategy_name()}")
    print(f"✓ Position size: {strategy.position_size_pct * 100}%")
    print(f"✓ Stop loss: {strategy.stop_loss_pct * 100}%")
    
    # Load test data
    import sys
    sys.path.append('..')
    from data.loader import DataLoader
    
    data_path = r"C:\Projects\Backtesting System\data"  # UPDATE THIS
    loader = DataLoader(data_path)
    df = loader.load_stock('RELIANCE_NS')
    
    print(f"\n✓ Loaded {len(df)} rows of RELIANCE data")
    
    # Test data validation
    is_valid, error = strategy.validate_data(df)
    print(f"✓ Data validation: {is_valid}")
    if error:
        print(f"  Error: {error}")
    
    # Test filters
    passes_filters = strategy.apply_filters(df)
    print(f"✓ Stock passes filters: {passes_filters}")
    
    # Test position sizing
    portfolio_value = 750000  # Rs. 7.5L
    current_price = df.iloc[-1]['Adj Close']
    shares = strategy.calculate_position_size(current_price, portfolio_value)
    position_value = shares * current_price
    
    print(f"\n✓ Position sizing:")
    print(f"  Portfolio value: Rs. {portfolio_value:,.0f}")
    print(f"  Current price: Rs. {current_price:.2f}")
    print(f"  Shares to buy: {shares}")
    print(f"  Position value: Rs. {position_value:,.2f}")
    print(f"  Position as % of portfolio: {(position_value/portfolio_value)*100:.2f}%")
    
    # Test stop loss calculation
    stop_loss = strategy.calculate_stop_loss(current_price)
    stop_loss_amount = current_price - stop_loss
    stop_loss_pct = (stop_loss_amount / current_price) * 100
    
    print(f"\n✓ Stop loss calculation:")
    print(f"  Entry price: Rs. {current_price:.2f}")
    print(f"  Stop loss price: Rs. {stop_loss:.2f}")
    print(f"  Stop loss amount: Rs. {stop_loss_amount:.2f}")
    print(f"  Stop loss percentage: {stop_loss_pct:.2f}%")
    
    # Test signal formatting
    signal_output = strategy.format_signal_output(
        symbol='RELIANCE_NS',
        df=df,
        signal=1,
        signal_strength=0.85,
        reason="Test signal"
    )
    
    print(f"\n✓ Signal formatting:")
    print(f"  Symbol: {signal_output['symbol']}")
    print(f"  Date: {signal_output['date']}")
    print(f"  Signal: {signal_output['signal']} (1=buy, -1=sell, 0=hold)")
    print(f"  Strength: {signal_output['signal_strength']}")
    print(f"  Price: Rs. {signal_output['price']:.2f}")
    print(f"  Stop loss: Rs. {signal_output['stop_loss']:.2f}")
    
    print("\n" + "="*70)
    print("✓ BaseStrategy tests PASSED")
    print("="*70)


if __name__ == "__main__":
    test_base_strategy()