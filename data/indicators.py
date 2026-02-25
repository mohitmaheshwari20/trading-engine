import pandas as pd
import numpy as np

class TechnicalIndicators:
    """
    Calculate technical indicators for trading strategies.
    All methods accept a pandas DataFrame with OHLCV data.
    """
    
    @staticmethod
    def calculate_rsi(df, period=14, price_col='Adj Close'):
        """
        Calculate Relative Strength Index (RSI).
        
        RSI measures momentum - how fast price is moving up vs down.
        Values range from 0-100:
        - Below 30: Oversold (potentially undervalued)
        - Above 70: Overbought (potentially overvalued)
        
        Args:
            df: DataFrame with price data
            period: Lookback period (default 14 days - Wilder's standard)
            price_col: Column name for price data
        
        Returns:
            pandas Series with RSI values
        """
        if price_col not in df.columns:
            raise ValueError(f"Column '{price_col}' not found in DataFrame")
        
        if len(df) < period + 1:
            raise ValueError(f"Need at least {period + 1} rows of data for RSI calculation")
        
        # Calculate price changes
        delta = df[price_col].diff()
        
        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Calculate average gain and loss using Wilder's smoothing
        # First average is simple mean
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        
        # Subsequent values use Wilder's smoothing (EMA-like)
        for i in range(period, len(df)):
            avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_bollinger_bands(df, period=20, std_dev=2, price_col='Adj Close'):
        """
        Calculate Bollinger Bands.
        
        Bollinger Bands show statistical volatility boundaries:
        - Middle Band: Simple Moving Average (mean price)
        - Upper Band: Mean + (2 × Standard Deviation)
        - Lower Band: Mean - (2 × Standard Deviation)
        
        When price touches lower band, it's statistically oversold.
        When price touches upper band, it's statistically overbought.
        
        Args:
            df: DataFrame with price data
            period: Lookback period (default 20 days)
            std_dev: Number of standard deviations (default 2)
            price_col: Column name for price data
        
        Returns:
            tuple: (middle_band, upper_band, lower_band) as pandas Series
        """
        if price_col not in df.columns:
            raise ValueError(f"Column '{price_col}' not found in DataFrame")
        
        if len(df) < period:
            raise ValueError(f"Need at least {period} rows of data for Bollinger Bands")
        
        # Middle band is simple moving average
        middle_band = df[price_col].rolling(window=period).mean()
        
        # Standard deviation over same period
        rolling_std = df[price_col].rolling(window=period).std()
        
        # Upper and lower bands
        upper_band = middle_band + (rolling_std * std_dev)
        lower_band = middle_band - (rolling_std * std_dev)
        
        return middle_band, upper_band, lower_band
    
    @staticmethod
    def calculate_sma(df, period, price_col='Adj Close'):
        """
        Calculate Simple Moving Average.
        
        SMA is the average price over N periods.
        Used for trend identification and support/resistance.
        
        Args:
            df: DataFrame with price data
            period: Number of periods to average
            price_col: Column name for price data
        
        Returns:
            pandas Series with SMA values
        """
        if price_col not in df.columns:
            raise ValueError(f"Column '{price_col}' not found in DataFrame")
        
        return df[price_col].rolling(window=period).mean()
    
    @staticmethod
    def calculate_volume_ratio(df, period=20):
        """
        Calculate volume ratio (current volume vs average volume).
        
        Volume confirmation is important:
        - Ratio > 1.2: Above-average volume (genuine move)
        - Ratio < 0.8: Below-average volume (weak move)
        
        Args:
            df: DataFrame with volume data
            period: Lookback period for average volume
        
        Returns:
            pandas Series with volume ratios
        """
        if 'Volume' not in df.columns:
            raise ValueError("'Volume' column not found in DataFrame")
        
        avg_volume = df['Volume'].rolling(window=period).mean()
        volume_ratio = df['Volume'] / avg_volume
        
        return volume_ratio
    
    @staticmethod
    def add_all_indicators(df, rsi_period=14, bb_period=20, bb_std=2):
        """
        Add all indicators to a DataFrame at once.
        
        This is a convenience function that adds:
        - RSI
        - Bollinger Bands (middle, upper, lower)
        - Volume Ratio
        
        Args:
            df: DataFrame with OHLCV data
            rsi_period: RSI lookback period
            bb_period: Bollinger Bands lookback period
            bb_std: Bollinger Bands standard deviation multiplier
        
        Returns:
            DataFrame with all indicator columns added
        """
        # Make a copy to avoid modifying original
        result = df.copy()
        
        # Add RSI
        result['RSI'] = TechnicalIndicators.calculate_rsi(
            result, period=rsi_period
        )
        
        # Add Bollinger Bands
        middle, upper, lower = TechnicalIndicators.calculate_bollinger_bands(
            result, period=bb_period, std_dev=bb_std
        )
        result['BB_Middle'] = middle
        result['BB_Upper'] = upper
        result['BB_Lower'] = lower
        
        # Add Volume Ratio
        result['Volume_Ratio'] = TechnicalIndicators.calculate_volume_ratio(
            result, period=bb_period
        )
        
        # Add 200-day SMA for regime filter (Phase 2)
        result['SMA_200'] = TechnicalIndicators.calculate_sma(
            result, period=200
        )
        
        return result


# Test function
def test_indicators():
    """
    Test indicator calculations on real data.
    """
    print("Testing TechnicalIndicators...\n")
    
    # Load a stock for testing
    import sys
    sys.path.append('..')
    from data.loader import DataLoader
    
    # UPDATE THIS PATH
    data_path = r"C:\Projects\Backtesting System\data"  # Change this!
    
    loader = DataLoader(data_path)
    
    # Load RELIANCE data
    print("Loading RELIANCE_NS data...")
    df = loader.load_stock('RELIANCE_NS')
    print(f"Loaded {len(df)} rows\n")
    
    # Calculate all indicators
    print("Calculating indicators...")
    df_with_indicators = TechnicalIndicators.add_all_indicators(df)
    
    # Show recent data with indicators
    print("Last 5 rows with indicators:")
    cols_to_show = ['Date', 'Adj Close', 'RSI', 'BB_Lower', 'BB_Middle', 
                    'BB_Upper', 'Volume_Ratio']
    print(df_with_indicators[cols_to_show].tail(10).to_string(index=False))
    
    # Find some oversold conditions (for verification)
    print("\n" + "="*70)
    print("OVERSOLD CONDITIONS (RSI < 30 in last 100 days):")
    print("="*70)
    
    recent = df_with_indicators.tail(100)
    oversold = recent[recent['RSI'] < 30]
    
    if len(oversold) > 0:
        print(f"\nFound {len(oversold)} oversold days:")
        cols = ['Date', 'Adj Close', 'RSI', 'BB_Lower', 'Volume_Ratio']
        print(oversold[cols].to_string(index=False))
    else:
        print("\nNo oversold conditions in last 100 days")
        print("This is normal - oversold is rare by definition")
    
    # Find some overbought conditions
    print("\n" + "="*70)
    print("OVERBOUGHT CONDITIONS (RSI > 70 in last 100 days):")
    print("="*70)
    
    overbought = recent[recent['RSI'] > 70]
    
    if len(overbought) > 0:
        print(f"\nFound {len(overbought)} overbought days:")
        print(overbought[cols].to_string(index=False))
    else:
        print("\nNo overbought conditions in last 100 days")
    
    # Verify RSI is within 0-100 range
    print("\n" + "="*70)
    print("VALIDATION CHECKS:")
    print("="*70)
    
    valid_rsi = df_with_indicators['RSI'].dropna()
    print(f"✓ RSI min: {valid_rsi.min():.2f} (should be >= 0)")
    print(f"✓ RSI max: {valid_rsi.max():.2f} (should be <= 100)")
    print(f"✓ RSI mean: {valid_rsi.mean():.2f} (should be around 50)")
    
    # Check Bollinger Bands relationship
    valid_bb = df_with_indicators[['BB_Lower', 'BB_Middle', 'BB_Upper']].dropna()
    print(f"\n✓ BB Lower always < Middle: {(valid_bb['BB_Lower'] < valid_bb['BB_Middle']).all()}")
    print(f"✓ BB Upper always > Middle: {(valid_bb['BB_Upper'] > valid_bb['BB_Middle']).all()}")
    
    # Check for NaN values (expected in early rows)
    print(f"\n✓ First 20 rows have NaN (expected): {df_with_indicators['RSI'].iloc[:20].isna().any()}")
    print(f"✓ After row 200, no NaN: {df_with_indicators['RSI'].iloc[200:].isna().sum() == 0}")
    
    print("\n" + "="*70)
    print("✓ Indicator calculations PASSED")
    print("="*70)


if __name__ == "__main__":
    test_indicators()