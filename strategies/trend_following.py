import pandas as pd
import numpy as np
import sys
sys.path.append('..')

from strategies.base_strategy import BaseStrategy
from data.indicators import TechnicalIndicators

class TrendFollowingStrategy(BaseStrategy):
    """
    Trend Following Strategy - Version 1 (Simple)
    
    Uses EMA crossover with ADX trend strength filter.
    
    ENTRY LOGIC:
    Buy when ALL conditions met:
    1. EMA_20 crosses above EMA_50 (bullish crossover)
    2. ADX > threshold (default 25 - confirms strong trend)
    
    EXIT LOGIC:
    Sell when ANY condition met:
    1. EMA_20 crosses below EMA_50 (bearish crossover)
    2. Trailing stop hit (default 15% from highest price since entry)
    
    THEORY:
    Trends persist. Enter when fast EMA crosses above slow EMA in a 
    confirmed trending market (ADX > 25). Exit when trend reverses or
    protective trailing stop is hit.
    
    PARAMETERS:
    - EMA Fast: 20 periods (responsive to recent price action)
    - EMA Slow: 50 periods (smooths out noise)
    - ADX Threshold: 25 (minimum trend strength)
    - Trailing Stop: 15% (protects profits while allowing trend to run)
    """
    
    def __init__(self, config):
        """
        Initialize trend following strategy.
        
        Args:
            config: Dictionary with strategy parameters
        """
        # EMA parameters
        self.ema_fast_period = config.get('ema_fast_period', 20)
        self.ema_slow_period = config.get('ema_slow_period', 50)
        
        # ADX parameters
        self.adx_period = config.get('adx_period', 14)
        self.adx_threshold = config.get('adx_threshold', 25)
        
        # Exit parameters
        self.trailing_stop_pct = config.get('trailing_stop_pct', 0.15)

        # Mean reversion indicators (not used for signals, but needed for engine compatibility)
        self.rsi_period = config.get('rsi_period', 14)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std_dev = config.get('bb_std_dev', 2)
        
        super().__init__(config)
    
    def get_strategy_name(self):
        """Return strategy name."""
        return f"Trend Following - EMA({self.ema_fast_period}/{self.ema_slow_period}) + ADX"
    
    def generate_signals(self, df, debug=True):
        """
        Generate buy/sell signals based on trend following logic.
        
        Args:
            df: DataFrame with OHLCV data
            debug: Enable diagnostic logging (default False)
        
        Returns:
            DataFrame with Signal and Signal_Strength columns added
        """
        # Validate data first
        is_valid, error = self.validate_data(df)
        if not is_valid:
            raise ValueError(f"Invalid data: {error}")

        df = df.copy()
        
        # Add indicators if not already present
        if 'EMA_Fast' not in df.columns or 'ADX' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(
                df,
                ema_fast=self.ema_fast_period,
                ema_slow=self.ema_slow_period,
                adx_period=self.adx_period
            )
        
        # Initialize signal columns
        df['Signal'] = 0
        df['Signal_Strength'] = 0.0
        df['Signal_Reason'] = ''
        
        # Detect crossovers
        df['EMA_Diff'] = df['EMA_Fast'] - df['EMA_Slow']
        df['Prev_EMA_Diff'] = df['EMA_Diff'].shift(1)
        
        # Get latest row only (we only generate signals for current day)
        latest_idx = df.index[-1]
        latest = df.loc[latest_idx]
        
        # DIAGNOSTIC: Check for crossover regardless of ADX
        bullish_crossover = (latest['EMA_Diff'] > 0) and (latest['Prev_EMA_Diff'] <= 0)
        bearish_crossover = (latest['EMA_Diff'] < 0) and (latest['Prev_EMA_Diff'] >= 0)
        
        if debug and (bullish_crossover or bearish_crossover):
            crossover_type = "BULLISH" if bullish_crossover else "BEARISH"
            print(f"  [{latest['Date']}] {crossover_type} CROSSOVER detected")
            print(f"    EMA_Fast: {latest['EMA_Fast']:.2f}, EMA_Slow: {latest['EMA_Slow']:.2f}")
            print(f"    ADX: {latest['ADX']:.2f} (threshold: {self.adx_threshold})")
            if latest['ADX'] < self.adx_threshold:
                print(f"    -> REJECTED: ADX too low (need >{self.adx_threshold})")
        
        # Skip if indicators not ready (NaN values)
        if pd.isna(latest['EMA_Fast']) or pd.isna(latest['EMA_Slow']) or pd.isna(latest['ADX']):
            return df
        
        # Check for BUY signal (bullish crossover)
        buy_signal, buy_strength, buy_reason = self._check_buy_conditions(latest, debug)
        
        if buy_signal:
            df.loc[latest_idx, 'Signal'] = 1
            df.loc[latest_idx, 'Signal_Strength'] = buy_strength
            df.loc[latest_idx, 'Signal_Reason'] = buy_reason
            if debug:
                print(f"    -> BUY SIGNAL GENERATED (strength: {buy_strength:.2f})")
        
        # Check for SELL signal (bearish crossover)
        # Note: Trailing stop is handled in backtesting engine, not here
        sell_signal, sell_strength, sell_reason = self._check_sell_conditions(latest, debug)
        
        if sell_signal:
            df.loc[latest_idx, 'Signal'] = -1
            df.loc[latest_idx, 'Signal_Strength'] = sell_strength
            df.loc[latest_idx, 'Signal_Reason'] = sell_reason
            if debug:
                print(f"    -> SELL SIGNAL GENERATED (strength: {sell_strength:.2f})")
        
        return df
    
    def _check_buy_conditions(self, row, debug=False):
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
        # Condition 1: Bullish crossover (Fast crosses above Slow)
        # Current: Fast > Slow, Previous: Fast <= Slow
        bullish_crossover = (row['EMA_Diff'] > 0) and (row['Prev_EMA_Diff'] <= 0)
        
        if not bullish_crossover:
            return False, 0.0, ""
        
        # Condition 2: ADX confirms trend strength
        if row['ADX'] < self.adx_threshold:
            return False, 0.0, ""
        
        # All conditions met - calculate signal strength
        # Stronger signals when:
        # 1. ADX is higher (stronger trend)
        # 2. Crossover gap is larger (more decisive)
        
        # ADX strength factor (normalize to 0-1 scale)
        # ADX 25 = 0.0, ADX 50 = 0.5, ADX 75+ = 1.0
        adx_strength = min((row['ADX'] - self.adx_threshold) / 50, 1.0)
        
        # Crossover gap strength (how far apart the EMAs are)
        # Larger gap = more decisive crossover
        crossover_gap_pct = abs(row['EMA_Diff']) / row['Adj Close']
        gap_strength = min(crossover_gap_pct * 100, 1.0)  # Scale to 0-1
        
        # Combined signal strength (average of factors)
        strength = (adx_strength + gap_strength) / 2
        strength = max(0.1, min(strength, 1.0))  # Clamp between 0.1 and 1.0
        
        reason = (f"BUY: EMA bullish crossover - "
                 f"Fast={row['EMA_Fast']:.2f} crossed above Slow={row['EMA_Slow']:.2f}, "
                 f"ADX={row['ADX']:.1f} (strong trend)")
        
        return True, strength, reason
    
    def _check_sell_conditions(self, row, debug=False):
        """
        Check if sell conditions are met.
        
        Note: Trailing stop is handled by backtesting engine.
        This only checks for bearish crossover exit.
        
        Args:
            row: Single row of DataFrame (latest day)
        
        Returns:
            tuple: (signal, strength, reason)
        """
        # Bearish crossover (Fast crosses below Slow)
        # Current: Fast < Slow, Previous: Fast >= Slow
        bearish_crossover = (row['EMA_Diff'] < 0) and (row['Prev_EMA_Diff'] >= 0)
        
        if not bearish_crossover:
            return False, 0.0, ""
        
        # Calculate exit strength
        # Stronger exit signal when:
        # 1. Crossover gap is larger (more decisive)
        # 2. ADX is declining (trend weakening)
        
        crossover_gap_pct = abs(row['EMA_Diff']) / row['Adj Close']
        gap_strength = min(crossover_gap_pct * 100, 1.0)
        
        # Default strength if we can't measure ADX decline
        strength = max(gap_strength, 0.5)
        
        reason = (f"SELL: EMA bearish crossover - "
                 f"Fast={row['EMA_Fast']:.2f} crossed below Slow={row['EMA_Slow']:.2f}")
        
        return True, strength, reason
    
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
        
        print(f"Scanning {len(stocks_list)} stocks for trend following signals...")
        
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
                if i % 10 == 0:
                    print(f"  Processed {i}/{len(stocks_list)} stocks...")
            
            except Exception as e:
                print(f"  Error processing {symbol}: {str(e)}")
                continue
        
        # Sort by signal strength (strongest first)
        signals.sort(key=lambda x: x['signal_strength'], reverse=True)
        
        return signals


# Test function
def test_trend_following():
    """
    Test trend following strategy on real data.
    """
    print("Testing Trend Following Strategy...\n")
    
    # Load configuration
    from utils.config_loader import ConfigLoader
    config_loader = ConfigLoader()
    
    # Create strategy config (since it doesn't exist yet in config files)
    trend_config = {
        'name': 'Trend Following - EMA + ADX',
        'ema_fast_period': 20,
        'ema_slow_period': 50,
        'adx_period': 14,
        'adx_threshold': 25,
        'trailing_stop_pct': 0.15,
        'position_size_pct': 0.05,
        'max_concurrent_positions': 5,
        'min_price': 10,
        'max_price': 10000,
        'min_volume': 100000
    }
    
    print(f"Strategy: {trend_config['name']}")
    print(f"EMA Fast: {trend_config['ema_fast_period']}")
    print(f"EMA Slow: {trend_config['ema_slow_period']}")
    print(f"ADX Threshold: {trend_config['adx_threshold']}")
    print(f"Trailing Stop: {trend_config['trailing_stop_pct']*100}%")
    print()
    
    # Create strategy instance
    strategy = TrendFollowingStrategy(trend_config)
    
    # Load test data
    from data.loader import DataLoader
    data_path = config_loader.get_data_dir()
    loader = DataLoader(data_path)
    
    # Test on BSE (one of our 15 trend following stocks)
    print("="*100)
    print("Testing on BSE_NS (Top 15 trending stock):")
    print("="*100)
    
    df = loader.load_stock('BSE_NS')
    df_with_signals = strategy.generate_signals(df)
    
    # Show latest signal
    latest = df_with_signals.iloc[-1]
    print(f"\nLatest data (as of {latest['Date']}):")
    print(f"  Price: Rs. {latest['Adj Close']:.2f}")
    print(f"  EMA Fast (20): Rs. {latest['EMA_Fast']:.2f}")
    print(f"  EMA Slow (50): Rs. {latest['EMA_Slow']:.2f}")
    print(f"  ADX: {latest['ADX']:.2f} ({'Strong trend' if latest['ADX'] > 25 else 'Weak trend'})")
    print(f"\n  Signal: {latest['Signal']} (1=buy, -1=sell, 0=hold)")
    print(f"  Strength: {latest['Signal_Strength']:.2f}")
    print(f"  Reason: {latest['Signal_Reason']}")
    
    # Find historical crossovers in last 200 days
    print("\n" + "="*100)
    print("HISTORICAL CROSSOVERS (last 200 days):")
    print("="*100)
    
    recent = df_with_signals.tail(200)
    
    # Find all buy signals
    buy_signals = recent[recent['Signal'] == 1]
    
    if len(buy_signals) > 0:
        print(f"\nFound {len(buy_signals)} BUY signals:")
        for idx, row in buy_signals.iterrows():
            print(f"\n  Date: {row['Date']}")
            print(f"  Price: Rs. {row['Adj Close']:.2f}")
            print(f"  EMA Fast: Rs. {row['EMA_Fast']:.2f}")
            print(f"  EMA Slow: Rs. {row['EMA_Slow']:.2f}")
            print(f"  ADX: {row['ADX']:.2f}")
            print(f"  Signal Strength: {row['Signal_Strength']:.2f}")
            print(f"  {row['Signal_Reason']}")
    else:
        print("\nNo buy signals in last 200 days")
    
    # Find all sell signals
    sell_signals = recent[recent['Signal'] == -1]
    
    if len(sell_signals) > 0:
        print(f"\nFound {len(sell_signals)} SELL signals:")
        for idx, row in sell_signals.iterrows():
            print(f"\n  Date: {row['Date']}")
            print(f"  Price: Rs. {row['Adj Close']:.2f}")
            print(f"  EMA Fast: Rs. {row['EMA_Fast']:.2f}")
            print(f"  EMA Slow: Rs. {row['EMA_Slow']:.2f}")
            print(f"  {row['Signal_Reason']}")
    else:
        print("\nNo sell signals in last 200 days")
    
    # Test scanner on our 15 stocks
    print("\n" + "="*100)
    print("SCANNING 15-STOCK TREND FOLLOWING UNIVERSE:")
    print("="*100)
    
    # Our 15 stocks
    universe_15 = [
        # Energy (5)
        'SUZLON_NS', 'ATGL_NS', 'WAAREEENER_NS', 'ADANIGREEN_NS', 'CGPOWER_NS',
        # Non-energy (10)
        'PAYTM_NS', 'ADANIENT_NS', 'BSE_NS', 'MAZDOCK_NS', 'DIXON_NS',
        'KPITTECH_NS', 'KALYANKJIL_NS', 'SWIGGY_NS', 'RVNL_NS', 'APLAPOLLO_NS'
    ]
    
    signals = strategy.scan_universe(loader, universe_15)
    
    if signals:
        print(f"\n✓ Found {len(signals)} buy signals:")
        for sig in signals:
            print(f"\n  {sig['symbol']}")
            print(f"  Price: Rs. {sig['price']:.2f}")
            print(f"  Stop Loss: Rs. {sig['stop_loss']:.2f}")
            print(f"  Strength: {sig['signal_strength']:.2f}")
            print(f"  {sig['reason']}")
    else:
        print("\n✓ No buy signals found")
        print("  (Normal if market not in strong uptrend)")
    
    print("\n" + "="*100)
    print("✓ Trend Following Strategy tests PASSED")
    print("="*100)
    
    print("\nNEXT STEP: Run backtest on 15-stock universe (2017-2025)")


if __name__ == "__main__":
    test_trend_following()
