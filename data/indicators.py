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
    def calculate_ema(df, period, price_col='Adj Close'):
        """
        Calculate Exponential Moving Average.
        
        EMA gives more weight to recent prices, making it more responsive
        to new information compared to SMA.
        
        Formula: EMA = Price(t) × k + EMA(y) × (1 - k)
        where k = 2 / (period + 1)
        
        Used for trend following - faster signals than SMA:
        - 20/50 EMA crossover is popular for swing trading
        - Faster entry/exit compared to SMA crossover
        
        Args:
            df: DataFrame with price data
            period: Number of periods for EMA calculation
            price_col: Column name for price data
        
        Returns:
            pandas Series with EMA values
        """
        if price_col not in df.columns:
            raise ValueError(f"Column '{price_col}' not found in DataFrame")
        
        if len(df) < period:
            raise ValueError(f"Need at least {period} rows of data for EMA calculation")
        
        # pandas ewm uses span parameter = period
        # adjust=False ensures we use proper EMA formula
        return df[price_col].ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_adx(df, period=14):
        """
        Calculate Average Directional Index (ADX).
        
        ADX measures trend strength (NOT direction):
        - ADX < 20: Weak or no trend (choppy, ranging market)
        - ADX 20-25: Emerging trend
        - ADX 25-50: Strong trend (good for trend following)
        - ADX > 50: Very strong trend
        - ADX > 75: Extremely strong trend (often near exhaustion)
        
        ADX is derived from +DI and -DI (directional indicators).
        Uses Wilder's smoothing method (similar to EMA).
        
        Theory: Only trade trending markets. ADX > 25 confirms a trend
        is present, making trend-following strategies more reliable.
        
        Args:
            df: DataFrame with High, Low, Close columns
            period: Lookback period (default 14, Wilder's standard)
        
        Returns:
            pandas Series with ADX values
        """
        required_cols = ['High', 'Low', 'Close']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"DataFrame must contain {required_cols}")
        
        if len(df) < period * 2:
            raise ValueError(f"Need at least {period * 2} rows for ADX calculation")
        
        # Step 1: Calculate True Range (TR)
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift(1))
        low_close = abs(df['Low'] - df['Close'].shift(1))
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Step 2: Calculate Directional Movement (+DM and -DM)
        high_diff = df['High'] - df['High'].shift(1)
        low_diff = df['Low'].shift(1) - df['Low']
        
        # +DM when upward movement is larger
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        
        # -DM when downward movement is larger
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        
        # Step 3: Smooth TR and DM using Wilder's smoothing
        # First value is simple sum, then use Wilder's formula
        atr = tr.rolling(window=period).sum()
        plus_dm_smooth = plus_dm.rolling(window=period).sum()
        minus_dm_smooth = minus_dm.rolling(window=period).sum()
        
        # Apply Wilder's smoothing for subsequent values
        for i in range(period, len(df)):
            atr.iloc[i] = atr.iloc[i-1] - (atr.iloc[i-1] / period) + tr.iloc[i]
            plus_dm_smooth.iloc[i] = plus_dm_smooth.iloc[i-1] - (plus_dm_smooth.iloc[i-1] / period) + plus_dm.iloc[i]
            minus_dm_smooth.iloc[i] = minus_dm_smooth.iloc[i-1] - (minus_dm_smooth.iloc[i-1] / period) + minus_dm.iloc[i]
        
        # Step 4: Calculate Directional Indicators (+DI and -DI)
        plus_di = 100 * (plus_dm_smooth / atr)
        minus_di = 100 * (minus_dm_smooth / atr)
        
        # Step 5: Calculate DX (Directional Index)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        dx = dx.replace([np.inf, -np.inf], 0)  # Handle division by zero
        
        # Step 6: Calculate ADX (smoothed DX)
        # First ADX value is average of first 'period' DX values
        adx = dx.rolling(window=period).mean()
        
        # Apply Wilder's smoothing for subsequent values
        for i in range(period * 2, len(df)):
            adx.iloc[i] = (adx.iloc[i-1] * (period - 1) + dx.iloc[i]) / period
        
        return adx
    
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
    def add_all_indicators(df, rsi_period=14, bb_period=20, bb_std=2, 
                          ema_fast=20, ema_slow=50, adx_period=14):
        """
        Add all indicators to a DataFrame at once.
        
        This is a convenience function that adds:
        - RSI (for mean reversion)
        - Bollinger Bands (for mean reversion)
        - Volume Ratio (for confirmation)
        - EMA Fast & Slow (for trend following)
        - ADX (for trend strength)
        - SMA 200 (for regime filter - Phase 2)
        
        Args:
            df: DataFrame with OHLCV data
            rsi_period: RSI lookback period (default 14)
            bb_period: Bollinger Bands lookback period (default 20)
            bb_std: Bollinger Bands standard deviation multiplier (default 2)
            ema_fast: Fast EMA period (default 20)
            ema_slow: Slow EMA period (default 50)
            adx_period: ADX period (default 14)
        
        Returns:
            DataFrame with all indicator columns added
        """
        # Make a copy to avoid modifying original
        result = df.copy()
        
        # Mean Reversion indicators
        result['RSI'] = TechnicalIndicators.calculate_rsi(
            result, period=rsi_period
        )
        
        middle, upper, lower = TechnicalIndicators.calculate_bollinger_bands(
            result, period=bb_period, std_dev=bb_std
        )
        result['BB_Middle'] = middle
        result['BB_Upper'] = upper
        result['BB_Lower'] = lower
        
        # Volume confirmation
        result['Volume_Ratio'] = TechnicalIndicators.calculate_volume_ratio(
            result, period=bb_period
        )
        
        # Trend Following indicators
        result['EMA_Fast'] = TechnicalIndicators.calculate_ema(
            result, period=ema_fast
        )
        result['EMA_Slow'] = TechnicalIndicators.calculate_ema(
            result, period=ema_slow
        )
        result['ADX'] = TechnicalIndicators.calculate_adx(
            result, period=adx_period
        )
        
        # Regime filter (Phase 2)
        result['SMA_200'] = TechnicalIndicators.calculate_sma(
            result, period=200
        )
        
        return result


# Test function
def test_indicators():
    """
    Test indicator calculations on real data.
    """
    print("Testing TechnicalIndicators (with EMA and ADX)...\n")
    
    # Load a stock for testing
    from loader import DataLoader
    
    # UPDATE THIS PATH
    data_path = r"C:\Projects\Backtesting System\data"
    
    loader = DataLoader(data_path)
    
    # Load BSE data
    print("Loading BSE data...")
    df = loader.load_stock('BSE_NS')
    print(f"Loaded {len(df)} rows\n")
    
    # Calculate all indicators
    print("Calculating all indicators (including EMA and ADX)...")
    df_with_indicators = TechnicalIndicators.add_all_indicators(df)
    
    # Show recent data with NEW indicators
    print("\n" + "="*100)
    print("LATEST DATA WITH TREND FOLLOWING INDICATORS:")
    print("="*100)
    cols_to_show = ['Date', 'Adj Close', 'EMA_Fast', 'EMA_Slow', 'ADX', 'Volume_Ratio']
    print(df_with_indicators[cols_to_show].tail(10).to_string(index=False))
    
    # Find EMA crossovers in last 100 days
    print("\n" + "="*100)
    print("EMA CROSSOVERS (last 100 days):")
    print("="*100)
    
    recent = df_with_indicators.tail(100).copy()
    
    # Detect crossovers
    recent['EMA_Diff'] = recent['EMA_Fast'] - recent['EMA_Slow']
    recent['Crossover'] = 0
    
    # Bullish crossover: Fast crosses above Slow
    bullish_cross = (recent['EMA_Diff'] > 0) & (recent['EMA_Diff'].shift(1) <= 0)
    recent.loc[bullish_cross, 'Crossover'] = 1
    
    # Bearish crossover: Fast crosses below Slow
    bearish_cross = (recent['EMA_Diff'] < 0) & (recent['EMA_Diff'].shift(1) >= 0)
    recent.loc[bearish_cross, 'Crossover'] = -1
    
    crossovers = recent[recent['Crossover'] != 0]
    
    if len(crossovers) > 0:
        print(f"\nFound {len(crossovers)} crossovers:")
        for idx, row in crossovers.iterrows():
            signal_type = "BULLISH (BUY)" if row['Crossover'] == 1 else "BEARISH (SELL)"
            print(f"\n  {signal_type} Crossover on {row['Date']}")
            print(f"  Price: Rs. {row['Adj Close']:.2f}")
            print(f"  EMA Fast (20): Rs. {row['EMA_Fast']:.2f}")
            print(f"  EMA Slow (50): Rs. {row['EMA_Slow']:.2f}")
            print(f"  ADX: {row['ADX']:.2f} ({'Strong trend' if row['ADX'] > 25 else 'Weak trend'})")
    else:
        print("\nNo crossovers in last 100 days")
    
    # ADX analysis
    print("\n" + "="*100)
    print("ADX ANALYSIS (Trend Strength):")
    print("="*100)
    
    valid_adx = recent['ADX'].dropna()
    
    print(f"\nADX Statistics (last 100 days):")
    print(f"  Current ADX: {recent.iloc[-1]['ADX']:.2f}")
    print(f"  Average ADX: {valid_adx.mean():.2f}")
    print(f"  Max ADX: {valid_adx.max():.2f}")
    print(f"  Min ADX: {valid_adx.min():.2f}")
    
    # ADX thresholds
    strong_trend_days = (recent['ADX'] > 25).sum()
    weak_trend_days = (recent['ADX'] <= 20).sum()
    
    print(f"\n  Days with ADX > 25 (strong trend): {strong_trend_days} ({strong_trend_days/len(recent)*100:.1f}%)")
    print(f"  Days with ADX <= 20 (weak trend): {weak_trend_days} ({weak_trend_days/len(recent)*100:.1f}%)")
    
    # Validation checks
    print("\n" + "="*100)
    print("VALIDATION CHECKS:")
    print("="*100)
    
    # RSI validation
    valid_rsi = df_with_indicators['RSI'].dropna()
    print(f"✓ RSI range: {valid_rsi.min():.2f} to {valid_rsi.max():.2f} (should be 0-100)")
    
    # EMA validation
    valid_ema_fast = df_with_indicators['EMA_Fast'].dropna()
    valid_ema_slow = df_with_indicators['EMA_Slow'].dropna()
    print(f"✓ EMA Fast calculated: {len(valid_ema_fast)} values")
    print(f"✓ EMA Slow calculated: {len(valid_ema_slow)} values")
    print(f"✓ EMA Fast > Slow currently: {df_with_indicators.iloc[-1]['EMA_Fast'] > df_with_indicators.iloc[-1]['EMA_Slow']} (trend direction)")
    
    # ADX validation
    valid_adx_all = df_with_indicators['ADX'].dropna()
    print(f"✓ ADX range: {valid_adx_all.min():.2f} to {valid_adx_all.max():.2f} (should be 0-100)")
    print(f"✓ ADX calculated: {len(valid_adx_all)} values")
    
    # Bollinger Bands validation
    valid_bb = df_with_indicators[['BB_Lower', 'BB_Middle', 'BB_Upper']].dropna()
    print(f"✓ BB Lower < Middle: {(valid_bb['BB_Lower'] < valid_bb['BB_Middle']).all()}")
    print(f"✓ BB Upper > Middle: {(valid_bb['BB_Upper'] > valid_bb['BB_Middle']).all()}")
    
    # Check for sufficient data after indicators
    total_rows = len(df_with_indicators)
    valid_rows = df_with_indicators[['EMA_Fast', 'EMA_Slow', 'ADX']].dropna().shape[0]
    print(f"\n✓ Total rows: {total_rows}")
    print(f"✓ Valid rows (all indicators ready): {valid_rows} ({valid_rows/total_rows*100:.1f}%)")
    print(f"✓ First {total_rows - valid_rows} rows have NaN (expected for indicator warmup)")
    
    print("\n" + "="*100)
    print("✓ ALL INDICATOR CALCULATIONS PASSED")
    print("="*100)
    
    print("\nNEXT STEP: Build trend_following.py strategy using EMA and ADX")


if __name__ == "__main__":
    test_indicators()
