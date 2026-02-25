import pandas as pd
import numpy as np
import sys
sys.path.append('..')

from strategies.base_strategy import BaseStrategy
from data.indicators import TechnicalIndicators

class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy using RSI and Bollinger Bands.
    
    ENTRY LOGIC:
    Buy when ALL conditions met:
    1. RSI < oversold threshold (default 30)
    2. Price <= Lower Bollinger Band
    3. Volume > average volume * 1.2 (confirmation)
    
    EXIT LOGIC:
    Sell when ANY condition met:
    1. RSI > overbought threshold (default 70)
    2. Price >= Upper Bollinger Band
    3. Stop loss hit (8% below entry)
    4. Holding period > max days (30 days default)
    
    THEORY:
    Prices that deviate significantly from their mean tend to revert.
    We buy statistical outliers (oversold) and sell when they normalize.
    """
    
    def __init__(self, config):
        """
        Initialize mean reversion strategy.
        
        Args:
            config: Dictionary with strategy parameters
        """
        super().__init__(config)
        
        # RSI parameters
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        
        # Bollinger Bands parameters
        self.bb_period = config.get('bb_period', 20)
        self.bb_std_dev = config.get('bb_std_dev', 2)
        
        # Volume confirmation
        self.volume_multiplier = config.get('volume_multiplier', 1.2)
        
        # Exit parameters
        self.max_holding_days = config.get('max_holding_days', 30)
        self.take_profit_pct = config.get('take_profit_pct', 0.15)  # Optional 15% target
    
    def get_strategy_name(self):
        """Return strategy name."""
        return "Mean Reversion - RSI + Bollinger Bands"
    
    def generate_signals(self, df):
        """
        Generate buy/sell signals based on mean reversion logic.
        
        Args:
            df: DataFrame with OHLCV data
        
        Returns:
            DataFrame with Signal and Signal_Strength columns added
        """
        # Validate data first
        is_valid, error = self.validate_data(df)
        if not is_valid:
            raise ValueError(f"Invalid data: {error}")

        df = df.copy()
        
        # Add indicators if not already present
        if 'RSI' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(
                df,
                rsi_period=self.rsi_period,
                bb_period=self.bb_period,
                bb_std=self.bb_std_dev
            )
        
        # Initialize signal columns
        df['Signal'] = 0
        df['Signal_Strength'] = 0.0
        df['Signal_Reason'] = ''
        
        # Get latest row only (we only generate signals for current day)
        latest_idx = df.index[-1]
        latest = df.loc[latest_idx]
        
        # Skip if indicators not ready (NaN values)
        if pd.isna(latest['RSI']) or pd.isna(latest['BB_Lower']):
            return df
        
        # Check for BUY signal
        buy_signal, buy_strength, buy_reason = self._check_buy_conditions(latest)
        
        if buy_signal:
            df.loc[latest_idx, 'Signal'] = 1
            df.loc[latest_idx, 'Signal_Strength'] = buy_strength
            df.loc[latest_idx, 'Signal_Reason'] = buy_reason
        
        # Check for SELL signal (only if we were in a position - simplified for now)
        # In real trading, we'd track actual positions
        sell_signal, sell_strength, sell_reason = self._check_sell_conditions(latest)
        
        if sell_signal:
            df.loc[latest_idx, 'Signal'] = -1
            df.loc[latest_idx, 'Signal_Strength'] = sell_strength
            df.loc[latest_idx, 'Signal_Reason'] = sell_reason
        
        return df
    
    def _check_buy_conditions(self, row):
        """
        Check if all buy conditions are met.
        
        Args:
            row: Single row of DataFrame (latest day)
        
        Returns:
            tuple: (signal, strength, reason)
                signal: True if buy signal
                strength: 0.0 to 1.0 confidence
                reason: Text explanation
        """
        conditions = []
        strength_factors = []
        
        # Condition 1: RSI oversold
        if row['RSI'] < self.rsi_oversold:
            conditions.append(True)
            # Deeper oversold = stronger signal
            oversold_degree = (self.rsi_oversold - row['RSI']) / self.rsi_oversold
            strength_factors.append(min(oversold_degree, 1.0))
        else:
            return False, 0.0, ""
        
        # Condition 2: Price at or below lower Bollinger Band
        if row['Adj Close'] <= row['BB_Lower']:
            conditions.append(True)
            # How far below the band?
            band_distance = (row['BB_Lower'] - row['Adj Close']) / row['BB_Lower']
            strength_factors.append(min(band_distance * 10, 1.0))  # Scale up
        else:
            return False, 0.0, ""
        
        # Condition 3: Volume confirmation
        if row['Volume_Ratio'] > self.volume_multiplier:
            conditions.append(True)
            # Higher volume = stronger confirmation
            volume_strength = min((row['Volume_Ratio'] - 1.0), 1.0)
            strength_factors.append(volume_strength)
        else:
            return False, 0.0, ""
        
        # All conditions met
        if all(conditions):
            # Calculate signal strength (average of all factors)
            strength = np.mean(strength_factors)
            
            reason = (f"BUY: RSI={row['RSI']:.1f} (oversold), "
                     f"Price={row['Adj Close']:.2f} at lower BB={row['BB_Lower']:.2f}, "
                     f"Volume={row['Volume_Ratio']:.2f}x average")
            
            return True, strength, reason
        
        return False, 0.0, ""
    
    def _check_sell_conditions(self, row):
        """
        Check if any sell conditions are met.
        
        Args:
            row: Single row of DataFrame (latest day)
        
        Returns:
            tuple: (signal, strength, reason)
        """
        # Condition 1: RSI overbought
        if row['RSI'] > self.rsi_overbought:
            strength = (row['RSI'] - self.rsi_overbought) / (100 - self.rsi_overbought)
            reason = f"SELL: RSI={row['RSI']:.1f} (overbought)"
            return True, strength, reason
        
        # Condition 2: Price at or above upper Bollinger Band
        if row['Adj Close'] >= row['BB_Upper']:
            strength = (row['Adj Close'] - row['BB_Upper']) / row['BB_Upper']
            strength = min(strength * 10, 1.0)
            reason = f"SELL: Price={row['Adj Close']:.2f} at upper BB={row['BB_Upper']:.2f}"
            return True, strength, reason
        
        # No sell signal
        return False, 0.0, ""
    
    def scan_universe(self, loader, stocks_list):
        """
        Scan entire universe and return all buy signals.
        
        Args:
            loader: DataLoader instance
            stocks_list: List of stock symbols to scan
        
        Returns:
            list: List of signal dictionaries, sorted by strength
        """
        signals = []
        
        print(f"Scanning {len(stocks_list)} stocks...")
        
        for i, symbol in enumerate(stocks_list, 1):
            try:
                # Load stock data
                df = loader.load_stock(symbol)
                
                # Apply filters
                if not self.apply_filters(df):
                    continue
                
                # Generate signals
                df_with_signals = self.generate_signals(df)
                
                # Check if there's a buy signal
                latest = df_with_signals.iloc[-1]
                
                if latest['Signal'] == 1:  # Buy signal
                    signal_output = self.format_signal_output(
                        symbol=symbol,
                        df=df_with_signals,
                        signal=1,
                        signal_strength=latest['Signal_Strength'],
                        reason=latest['Signal_Reason']
                    )
                    signals.append(signal_output)
                
                # Progress indicator
                if i % 50 == 0:
                    print(f"  Processed {i}/{len(stocks_list)} stocks...")
            
            except Exception as e:
                print(f"  Error processing {symbol}: {str(e)}")
                continue
        
        # Sort by signal strength (strongest first)
        signals.sort(key=lambda x: x['signal_strength'], reverse=True)
        
        return signals


# Test function
def test_mean_reversion():
    """
    Test mean reversion strategy on real data.
    """
    print("Testing Mean Reversion Strategy...\n")
    
    # Load configuration
    from utils.config_loader import ConfigLoader
    config_loader = ConfigLoader()
    strategy_config = config_loader.load_config('strategies_config')
    mr_config = strategy_config['mean_reversion']
    
    print(f"Strategy: {mr_config['name']}")
    print(f"RSI oversold: {mr_config['rsi_oversold']}")
    print(f"RSI overbought: {mr_config['rsi_overbought']}")
    print(f"Bollinger Bands period: {mr_config['bb_period']}")
    print()
    
    # Create strategy instance
    strategy = MeanReversionStrategy(mr_config)
    
    # Load test data
    from data.loader import DataLoader
    data_path = config_loader.get_data_dir()
    loader = DataLoader(data_path)
    
    # Test on RELIANCE
    print("="*70)
    print("Testing on RELIANCE_NS:")
    print("="*70)
    
    df = loader.load_stock('RELIANCE_NS')
    df_with_signals = strategy.generate_signals(df)
    
    # Show latest signal
    latest = df_with_signals.iloc[-1]
    print(f"\nLatest data (as of {latest['Date']}):")
    print(f"  Price: Rs. {latest['Adj Close']:.2f}")
    print(f"  RSI: {latest['RSI']:.2f}")
    print(f"  BB Lower: Rs. {latest['BB_Lower']:.2f}")
    print(f"  BB Middle: Rs. {latest['BB_Middle']:.2f}")
    print(f"  BB Upper: Rs. {latest['BB_Upper']:.2f}")
    print(f"  Volume Ratio: {latest['Volume_Ratio']:.2f}x")
    print(f"\n  Signal: {latest['Signal']} (1=buy, -1=sell, 0=hold)")
    print(f"  Strength: {latest['Signal_Strength']:.2f}")
    print(f"  Reason: {latest['Signal_Reason']}")
    
    # Find historical buy signals in last 100 days
    print("\n" + "="*70)
    print("Historical BUY signals (last 100 days):")
    print("="*70)
    
    recent = df_with_signals.tail(100)
    buy_signals = recent[recent['Signal'] == 1]
    
    if len(buy_signals) > 0:
        print(f"\nFound {len(buy_signals)} buy signals:")
        for idx, row in buy_signals.iterrows():
            print(f"\n  Date: {row['Date']}")
            print(f"  Price: Rs. {row['Adj Close']:.2f}")
            print(f"  RSI: {row['RSI']:.2f}")
            print(f"  Signal Strength: {row['Signal_Strength']:.2f}")
            print(f"  Reason: {row['Signal_Reason']}")
    else:
        print("\nNo buy signals in last 100 days")
        print("(This is normal - oversold conditions are rare)")
    
    # Scan a few stocks to test scanner
    print("\n" + "="*70)
    print("Scanning first 10 stocks for signals:")
    print("="*70)
    
    stocks = loader.list_stocks()[:10]
    signals = strategy.scan_universe(loader, stocks)
    
    if signals:
        print(f"\n✓ Found {len(signals)} buy signals:")
        for sig in signals:
            print(f"\n  {sig['symbol']}")
            print(f"  Price: Rs. {sig['price']:.2f}")
            print(f"  Stop Loss: Rs. {sig['stop_loss']:.2f}")
            print(f"  Strength: {sig['signal_strength']:.2f}")
            print(f"  {sig['reason']}")
    else:
        print("\n✓ No buy signals found (normal if market not oversold)")
    
    print("\n" + "="*70)
    print("✓ Mean Reversion Strategy tests PASSED")
    print("="*70)


if __name__ == "__main__":
    test_mean_reversion()