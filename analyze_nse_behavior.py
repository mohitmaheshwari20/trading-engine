"""
NSE Stock Behavior Analysis
============================
Analyzes Nifty 200 stocks (2017-2025) to identify:
1. Momentum/autocorrelation patterns
2. Mean reversion behavior
3. Trend persistence
4. Market regime dependencies

Purpose: Determine which stocks are suitable for which strategies
BEFORE building those strategies.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

DATA_DIR = Path(r"C:\Projects\Backtesting System\data")
UNIVERSE_FILE = Path(r"C:\Projects\Backtesting System\nifty200_universe.csv")
START_DATE = '2017-01-01'
END_DATE = '2026-02-19'

# Analysis parameters (baseline - can be adjusted based on results)
AUTOCORR_LAGS = [1, 5, 20]  # Days
MA_PERIOD = 20  # For mean reversion
MA_FAST = 20  # For trend detection
MA_SLOW = 50  # For trend detection
STD_THRESHOLD = 1.0  # Standard deviations for mean reversion

# Market regimes for analysis
REGIMES = {
    'pre_covid': ('2017-01-01', '2019-12-31'),
    'covid': ('2020-01-01', '2020-12-31'),
    'recovery': ('2021-01-01', '2022-12-31'),
    'recent': ('2023-01-01', '2026-02-19')
}

print("="*80)
print("NSE STOCK BEHAVIOR ANALYSIS")
print("="*80)
print(f"Period: {START_DATE} to {END_DATE}")
print(f"Universe: Nifty 200")
print(f"\nParameters:")
print(f"  Autocorrelation lags: {AUTOCORR_LAGS}")
print(f"  Mean reversion MA: {MA_PERIOD} days, {STD_THRESHOLD} std threshold")
print(f"  Trend MAs: {MA_FAST}/{MA_SLOW}")
print()

# ============================================================================
# STEP 1: LOAD DATA
# ============================================================================

print("STEP 1: Loading Data")
print("-" * 80)

# Load universe
print("Loading Nifty 200 universe...")
universe_df = pd.read_csv(UNIVERSE_FILE)
symbols = universe_df['symbol'].tolist()[1:]  # Skip first row (NIFTY 200.NS)
print(f"Found {len(symbols)} stocks in universe")

# Load stock data
print("\nLoading stock price data...")
stock_data = {}
failed_loads = []

for i, symbol in enumerate(symbols, 1):
    try:
        # Convert symbol from dot notation (RELIANCE.NS) to underscore (RELIANCE_NS) for filename
        filename = symbol.replace('.', '_')
        filepath = DATA_DIR / f"{filename}.csv"
        if filepath.exists():
            df = pd.read_csv(filepath)
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date')
            
            # Filter to analysis period
            df = df[(df['Date'] >= START_DATE) & (df['Date'] <= END_DATE)]
            
            # Require minimum 100 days of data
            if len(df) > 100:
                stock_data[symbol] = df
                
                if i % 50 == 0:
                    print(f"  Loaded {i}/{len(symbols)} stocks...")
        else:
            failed_loads.append(symbol)
    except Exception as e:
        failed_loads.append(symbol)

print(f"\nSuccessfully loaded: {len(stock_data)} stocks")
print(f"Failed/insufficient data: {len(failed_loads)} stocks")

# Calculate returns for all stocks
print("\nCalculating returns...")
for symbol, df in stock_data.items():
    df['Return'] = df['Adj Close'].pct_change()
    df['Return_5d'] = df['Adj Close'].pct_change(5)
    df['Return_20d'] = df['Adj Close'].pct_change(20)

# Debug: Check a sample stock
if len(stock_data) > 0:
    sample_symbol = list(stock_data.keys())[0]
    sample_df = stock_data[sample_symbol]
    print(f"  Sample stock: {sample_symbol}")
    print(f"  Rows: {len(sample_df)}, Columns: {list(sample_df.columns)}")
    print(f"  Has valid returns: {sample_df['Return'].notna().sum()} / {len(sample_df)}")

print()

# ============================================================================
# STEP 2: MOMENTUM ANALYSIS (Autocorrelation)
# ============================================================================

print("="*80)
print("STEP 2: MOMENTUM ANALYSIS")
print("="*80)
print("Testing if past returns predict future returns (autocorrelation)")
print()

momentum_results = []
error_count = 0

for symbol, df in stock_data.items():
    df_clean = df.dropna(subset=['Return'])
    
    if len(df_clean) < 100:
        continue
    
    try:
        # Calculate autocorrelation at different lags
        autocorr_1d = df_clean['Return'].autocorr(lag=1)
        autocorr_5d = df_clean['Return'].autocorr(lag=5)
        autocorr_20d = df_clean['Return'].autocorr(lag=20)
        
        # Statistical test: does today's return predict tomorrow's?
        returns_today = df_clean['Return'].values[:-1]
        returns_tomorrow = df_clean['Return'].values[1:]
        correlation, p_value = stats.pearsonr(returns_today, returns_tomorrow)
        
        # Classify momentum strength
        if autocorr_1d > 0.10 and p_value < 0.05:
            strength = "Strong Momentum"
        elif autocorr_1d > 0.05 and p_value < 0.10:
            strength = "Moderate Momentum"
        elif autocorr_1d < -0.05:
            strength = "Mean Reverting"
        else:
            strength = "Weak/Random"
        
        momentum_results.append({
            'symbol': symbol,
            'autocorr_1d': autocorr_1d,
            'autocorr_5d': autocorr_5d,
            'autocorr_20d': autocorr_20d,
            'correlation': correlation,
            'p_value': p_value,
            'strength': strength
        })
    except Exception as e:
        error_count += 1
        if error_count <= 3:  # Show first 3 errors
            print(f"  Error analyzing {symbol}: {str(e)}")
        continue

if error_count > 3:
    print(f"  ... and {error_count - 3} more errors")
print()

df_momentum = pd.DataFrame(momentum_results)

if len(df_momentum) == 0:
    print("ERROR: No stocks successfully analyzed for momentum!")
    print("Check if stock data has valid returns calculated.")
    print()
else:
    print(f"Analyzed {len(df_momentum)} stocks\n")
    print("Distribution by Momentum Strength:")
    print(df_momentum['strength'].value_counts())
if len(df_momentum) > 0:
    print()
    
    print("Top 15 Momentum Stocks (1-day autocorrelation):")
    top_momentum = df_momentum.nlargest(min(15, len(df_momentum)), 'autocorr_1d')
    for idx, row in top_momentum.iterrows():
        sig = "***" if row['p_value'] < 0.01 else "**" if row['p_value'] < 0.05 else "*"
        print(f"  {row['symbol']:20} Autocorr: {row['autocorr_1d']:+.4f} {sig} (p={row['p_value']:.4f})")
    
    print("\nTop 15 Mean Reverting Stocks (negative autocorrelation):")
    bottom_momentum = df_momentum.nsmallest(min(15, len(df_momentum)), 'autocorr_1d')
    for idx, row in bottom_momentum.iterrows():
        print(f"  {row['symbol']:20} Autocorr: {row['autocorr_1d']:+.4f}")

print()

# ============================================================================
# STEP 3: MEAN REVERSION ANALYSIS
# ============================================================================

print("="*80)
print("STEP 3: MEAN REVERSION ANALYSIS")
print("="*80)
print(f"Testing if stocks bounce from {STD_THRESHOLD} std deviations from {MA_PERIOD}-day MA")
print()

mean_reversion_results = []

for symbol, df in stock_data.items():
    # Calculate distance from moving average
    df[f'SMA_{MA_PERIOD}'] = df['Adj Close'].rolling(MA_PERIOD).mean()
    df['Distance_MA'] = (df['Adj Close'] - df[f'SMA_{MA_PERIOD}']) / df[f'SMA_{MA_PERIOD}'] * 100
    df['Next_Return'] = df['Return'].shift(-1)
    
    df_clean = df.dropna(subset=['Distance_MA', 'Next_Return'])
    
    if len(df_clean) < 100:
        continue
    
    try:
        # Identify oversold/overbought conditions
        std_distance = df_clean['Distance_MA'].std()
        threshold = STD_THRESHOLD * std_distance
        
        oversold = df_clean[df_clean['Distance_MA'] < -threshold]
        overbought = df_clean[df_clean['Distance_MA'] > threshold]
        
        # Check bounce rates
        oversold_bounce_rate = (oversold['Next_Return'] > 0).mean() if len(oversold) > 10 else np.nan
        overbought_fall_rate = (overbought['Next_Return'] < 0).mean() if len(overbought) > 10 else np.nan
        
        # Mean reversion score (average of both rates)
        if pd.notna(oversold_bounce_rate) and pd.notna(overbought_fall_rate):
            mr_score = (oversold_bounce_rate + overbought_fall_rate) / 2
        else:
            mr_score = np.nan
        
        # Classify
        if pd.notna(mr_score):
            if mr_score > 0.57:
                strength = "Strong Mean Reversion"
            elif mr_score > 0.53:
                strength = "Moderate Mean Reversion"
            else:
                strength = "Weak/Trending"
        else:
            strength = "Insufficient Data"
        
        mean_reversion_results.append({
            'symbol': symbol,
            'oversold_bounce_rate': oversold_bounce_rate,
            'overbought_fall_rate': overbought_fall_rate,
            'mr_score': mr_score,
            'strength': strength,
            'num_oversold': len(oversold),
            'num_overbought': len(overbought)
        })
    except:
        continue

df_mr = pd.DataFrame(mean_reversion_results)
df_mr_valid = df_mr[df_mr['strength'] != 'Insufficient Data']

if len(df_mr_valid) == 0:
    print("ERROR: No stocks successfully analyzed for mean reversion!")
    print()
else:
    print(f"Analyzed {len(df_mr_valid)} stocks with sufficient data\n")
    print("Distribution by Mean Reversion Strength:")
    print(df_mr_valid['strength'].value_counts())
    print()
    
    print("Top 15 Mean Reverting Stocks:")
    top_mr = df_mr_valid.nlargest(min(15, len(df_mr_valid)), 'mr_score')
    for idx, row in top_mr.iterrows():
        print(f"  {row['symbol']:20} MR Score: {row['mr_score']:.3f} "
              f"(Oversold bounce: {row['oversold_bounce_rate']:.1%}, "
              f"Overbought fall: {row['overbought_fall_rate']:.1%})")
    
    print()

# ============================================================================
# STEP 4: TREND PERSISTENCE ANALYSIS
# ============================================================================

print("="*80)
print("STEP 4: TREND PERSISTENCE ANALYSIS")
print("="*80)
print(f"Testing trend quality using {MA_FAST}/{MA_SLOW} MA crossover")
print()

trend_results = []

for symbol, df in stock_data.items():
    # Calculate moving averages
    df['SMA_Fast'] = df['Adj Close'].rolling(MA_FAST).mean()
    df['SMA_Slow'] = df['Adj Close'].rolling(MA_SLOW).mean()
    
    # Define trend signals
    df['Trend'] = 0
    df.loc[df['SMA_Fast'] > df['SMA_Slow'], 'Trend'] = 1  # Uptrend
    df.loc[df['SMA_Fast'] < df['SMA_Slow'], 'Trend'] = -1  # Downtrend
    
    df_clean = df.dropna(subset=['Trend'])
    
    if len(df_clean) < 100:
        continue
    
    # Detect trend changes
    df_clean['Trend_Change'] = df_clean['Trend'].diff()
    crossovers = df_clean[df_clean['Trend_Change'] != 0].copy()
    
    if len(crossovers) < 5:
        continue
    
    # Measure returns during each trend
    uptrends = []
    downtrends = []
    
    for i in range(len(crossovers) - 1):
        start_idx = crossovers.index[i]
        end_idx = crossovers.index[i + 1]
        
        trend_signal = df_clean.loc[start_idx, 'Trend']
        start_price = df_clean.loc[start_idx, 'Adj Close']
        end_price = df_clean.loc[end_idx, 'Adj Close']
        
        trend_return = (end_price - start_price) / start_price * 100
        trend_days = (df_clean.loc[end_idx, 'Date'] - df_clean.loc[start_idx, 'Date']).days
        
        if trend_signal == 1:
            uptrends.append({'return': trend_return, 'days': trend_days})
        elif trend_signal == -1:
            downtrends.append({'return': trend_return, 'days': trend_days})
    
    if len(uptrends) > 0 and len(downtrends) > 0:
        avg_uptrend_return = np.mean([t['return'] for t in uptrends])
        avg_downtrend_return = np.mean([t['return'] for t in downtrends])
        avg_uptrend_days = np.mean([t['days'] for t in uptrends])
        
        # Trend quality: positive during uptrends, negative during downtrends
        trend_quality = avg_uptrend_return - avg_downtrend_return
        
        trend_results.append({
            'symbol': symbol,
            'num_uptrends': len(uptrends),
            'num_downtrends': len(downtrends),
            'avg_uptrend_return': avg_uptrend_return,
            'avg_downtrend_return': avg_downtrend_return,
            'avg_uptrend_days': avg_uptrend_days,
            'trend_quality': trend_quality
        })

df_trend = pd.DataFrame(trend_results)

if len(df_trend) == 0:
    print("ERROR: No stocks successfully analyzed for trend persistence!")
    print()
else:
    print(f"Analyzed {len(df_trend)} stocks\n")
    
    print("Top 15 Trending Stocks (by trend quality):")
    top_trend = df_trend.nlargest(min(15, len(df_trend)), 'trend_quality')
    for idx, row in top_trend.iterrows():
        print(f"  {row['symbol']:20} Quality: {row['trend_quality']:+7.2f}% "
              f"(Uptrends: {row['avg_uptrend_return']:+5.1f}%, "
              f"Downtrends: {row['avg_downtrend_return']:+5.1f}%, "
              f"Avg {row['avg_uptrend_days']:.0f} days)")
    
    print()

# ============================================================================
# STEP 5: REGIME ANALYSIS
# ============================================================================

print("="*80)
print("STEP 5: REGIME ANALYSIS")
print("="*80)
print("Testing if patterns are consistent across different market periods")
print()

regime_summary = []

for regime_name, (start, end) in REGIMES.items():
    print(f"{regime_name.upper().replace('_', ' ')} ({start} to {end}):")
    
    regime_autocorr = []
    regime_mr_scores = []
    
    for symbol, df in stock_data.items():
        df_regime = df[(df['Date'] >= start) & (df['Date'] <= end)].copy()
        
        if len(df_regime) < 50:
            continue
        
        # Momentum in this regime
        try:
            autocorr = df_regime['Return'].autocorr(lag=1)
            if pd.notna(autocorr):
                regime_autocorr.append(autocorr)
        except:
            pass
        
        # Mean reversion in this regime
        try:
            df_regime['SMA'] = df_regime['Adj Close'].rolling(MA_PERIOD).mean()
            df_regime['Distance'] = (df_regime['Adj Close'] - df_regime['SMA']) / df_regime['SMA'] * 100
            df_regime['Next_Return'] = df_regime['Return'].shift(-1)
            
            df_clean = df_regime.dropna(subset=['Distance', 'Next_Return'])
            
            if len(df_clean) > 20:
                std_distance = df_clean['Distance'].std()
                oversold = df_clean[df_clean['Distance'] < -std_distance]
                overbought = df_clean[df_clean['Distance'] > std_distance]
                
                if len(oversold) > 5 and len(overbought) > 5:
                    bounce = (oversold['Next_Return'] > 0).mean()
                    fall = (overbought['Next_Return'] < 0).mean()
                    mr_score = (bounce + fall) / 2
                    regime_mr_scores.append(mr_score)
        except:
            pass
    
    avg_autocorr = np.mean(regime_autocorr) if regime_autocorr else 0
    avg_mr = np.mean(regime_mr_scores) if regime_mr_scores else 0
    
    print(f"  Stocks analyzed: {len(regime_autocorr)}")
    print(f"  Avg 1-day autocorrelation: {avg_autocorr:+.4f}")
    print(f"  Avg mean reversion score: {avg_mr:.3f}")
    
    if avg_autocorr > 0.05:
        print(f"  → Momentum/trend strategies favored")
    if avg_mr > 0.53:
        print(f"  → Mean reversion strategies favored")
    if abs(avg_autocorr) < 0.03 and avg_mr < 0.52:
        print(f"  → Market appears random/choppy")
    
    print()
    
    regime_summary.append({
        'regime': regime_name,
        'autocorr': avg_autocorr,
        'mr_score': avg_mr
    })

# ============================================================================
# STEP 6: SUMMARY & RECOMMENDATIONS
# ============================================================================

print("="*80)
print("SUMMARY & RECOMMENDATIONS")
print("="*80)
print()

# Identify strategy-specific universes
strong_momentum = df_momentum[df_momentum['autocorr_1d'] > 0.08]['symbol'].tolist() if len(df_momentum) > 0 else []
strong_mr = df_mr_valid[df_mr_valid['mr_score'] > 0.55]['symbol'].tolist() if len(df_mr_valid) > 0 else []
strong_trend = df_trend.nlargest(min(30, len(df_trend)), 'trend_quality')['symbol'].tolist() if len(df_trend) > 0 else []

print("STRATEGY-SPECIFIC UNIVERSES:")
print()

print(f"1. TREND FOLLOWING CANDIDATES:")
print(f"   {len(strong_trend)} stocks showing strong trending behavior")
if len(strong_trend) > 0:
    print(f"   Top 10: {', '.join(strong_trend[:10])}")
print()

print(f"2. MEAN REVERSION CANDIDATES:")
print(f"   {len(strong_mr)} stocks showing strong mean reversion")
if len(strong_mr) > 0:
    print(f"   Top 10: {', '.join(strong_mr[:10])}")
print()

print(f"3. MOMENTUM CANDIDATES:")
print(f"   {len(strong_momentum)} stocks showing strong momentum/autocorrelation")
if len(strong_momentum) > 0:
    print(f"   Top 10: {', '.join(strong_momentum[:10])}")
print()

# Strategy overlaps
overlap_trend_momentum = set(strong_trend) & set(strong_momentum)
overlap_all = set(strong_trend) & set(strong_momentum) & set(strong_mr)

print("OVERLAPS:")
print(f"  Trend + Momentum: {len(overlap_trend_momentum)} stocks (expected - both capture directional moves)")
print(f"  All three strategies: {len(overlap_all)} stocks (rare - conflicting behaviors)")
print()

print("REGIME INSIGHTS:")
df_regime = pd.DataFrame(regime_summary)
for idx, row in df_regime.iterrows():
    print(f"  {row['regime']:15} Autocorr: {row['autocorr']:+.4f}, MR Score: {row['mr_score']:.3f}")
print()

# Save detailed results
print("="*80)
print("SAVING RESULTS")
print("="*80)

# Save strategy universes
trend_universe = pd.DataFrame({'symbol': strong_trend})
trend_universe.to_csv('trend_following_universe.csv', index=False)
print(f"Saved: trend_following_universe.csv ({len(strong_trend)} stocks)")

mr_universe = pd.DataFrame({'symbol': strong_mr})
mr_universe.to_csv('mean_reversion_universe.csv', index=False)
print(f"Saved: mean_reversion_universe.csv ({len(strong_mr)} stocks)")

momentum_universe = pd.DataFrame({'symbol': strong_momentum})
momentum_universe.to_csv('momentum_universe.csv', index=False)
print(f"Saved: momentum_universe.csv ({len(strong_momentum)} stocks)")

# Save full analysis
if len(df_momentum) > 0:
    df_momentum.to_csv('momentum_analysis_full.csv', index=False)
    print(f"Saved: momentum_analysis_full.csv")

if len(df_mr_valid) > 0:
    df_mr_valid.to_csv('mean_reversion_analysis_full.csv', index=False)
    print(f"Saved: mean_reversion_analysis_full.csv")

if len(df_trend) > 0:
    df_trend.to_csv('trend_analysis_full.csv', index=False)
    print(f"Saved: trend_analysis_full.csv")

if len(df_momentum) == 0 and len(df_mr_valid) == 0 and len(df_trend) == 0:
    print("WARNING: No analysis results to save!")

print()

print("="*80)
print("ANALYSIS COMPLETE")
print("="*80)
print()
print("NEXT STEPS:")
print("1. Review the strategy-specific universes")
print("2. Decide which strategy to test first based on:")
print("   - Number of suitable stocks")
print("   - Regime consistency")
print("   - Your preference")
print("3. Build and backtest that strategy on its optimal universe")
print()
