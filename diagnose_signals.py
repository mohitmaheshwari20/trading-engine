"""
Diagnostic script to analyze why trend following strategy generates 0 signals.
Runs on a single stock and shows all crossovers and ADX values.
"""

import pandas as pd
from data.loader import DataLoader
from utils.config_loader import ConfigLoader
from strategies.trend_following import TrendFollowingStrategy
from data.indicators import TechnicalIndicators

def analyze_stock(symbol, start_date='2017-01-01', end_date='2025-12-31'):
    """
    Analyze a single stock to see crossovers and ADX filtering.
    """
    print("="*100)
    print(f"DIAGNOSTIC ANALYSIS: {symbol}")
    print("="*100)
    
    # Load configuration and data
    config_loader = ConfigLoader()
    main_config = config_loader.load_config('config')
    data_path = main_config['data']['source_dir']
    
    # Create strategy config
    trend_config = {
        'name': 'Trend Following - Diagnostic',
        'ema_fast_period': 20,
        'ema_slow_period': 50,
        'adx_period': 14,
        'adx_threshold': 25,
        'trailing_stop_pct': 0.15,
        'position_size_pct': 0.05,
        'max_concurrent_positions': 5,
        'stop_loss_pct': 0.15,
        'min_price': 10,
        'max_price': 10000,
        'min_volume': 100000
    }
    
    strategy = TrendFollowingStrategy(trend_config)
    
    # Load stock data
    loader = DataLoader(data_path)
    print(f"\nLoading {symbol} data...")
    df = loader.load_stock(symbol)
    
    # Filter to date range
    df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]
    print(f"Data period: {df['Date'].min()} to {df['Date'].max()}")
    print(f"Total days: {len(df)}\n")
    
    # Add indicators
    print("Calculating indicators...")
    df = TechnicalIndicators.add_all_indicators(
        df,
        ema_fast=20,
        ema_slow=50,
        adx_period=14
    )
    
    # Detect crossovers
    df['EMA_Diff'] = df['EMA_Fast'] - df['EMA_Slow']
    df['Prev_EMA_Diff'] = df['EMA_Diff'].shift(1)
    
    # Bullish crossovers
    df['Bullish_Cross'] = (df['EMA_Diff'] > 0) & (df['Prev_EMA_Diff'] <= 0)
    
    # Bearish crossovers
    df['Bearish_Cross'] = (df['EMA_Diff'] < 0) & (df['Prev_EMA_Diff'] >= 0)
    
    # Count crossovers
    bullish_crosses = df[df['Bullish_Cross'] == True]
    bearish_crosses = df[df['Bearish_Cross'] == True]
    
    print("="*100)
    print("CROSSOVER SUMMARY")
    print("="*100)
    print(f"Total bullish crossovers: {len(bullish_crosses)}")
    print(f"Total bearish crossovers: {len(bearish_crosses)}")
    
    # Analyze bullish crossovers with ADX
    if len(bullish_crosses) > 0:
        print("\n" + "="*100)
        print("BULLISH CROSSOVERS (EMA_20 crosses ABOVE EMA_50)")
        print("="*100)
        print(f"{'Date':<12} {'Price':>8} {'EMA_20':>8} {'EMA_50':>8} {'ADX':>6} {'ADX>=25':>8} {'Signal':>8}")
        print("-"*100)
        
        signals_passed = 0
        signals_failed = 0
        
        for idx, row in bullish_crosses.iterrows():
            adx_pass = row['ADX'] >= 25
            signal = "BUY" if adx_pass else "REJECT"
            
            if adx_pass:
                signals_passed += 1
            else:
                signals_failed += 1
            
            print(f"{str(row['Date'])[:10]:<12} "
                  f"{row['Adj Close']:8.2f} "
                  f"{row['EMA_Fast']:8.2f} "
                  f"{row['EMA_Slow']:8.2f} "
                  f"{row['ADX']:6.2f} "
                  f"{'YES' if adx_pass else 'NO':>8} "
                  f"{signal:>8}")
        
        print("-"*100)
        print(f"Signals PASSED ADX filter: {signals_passed}")
        print(f"Signals REJECTED by ADX: {signals_failed}")
        print(f"Pass rate: {(signals_passed/len(bullish_crosses)*100):.1f}%")
    
    # Analyze bearish crossovers
    if len(bearish_crosses) > 0:
        print("\n" + "="*100)
        print("BEARISH CROSSOVERS (EMA_20 crosses BELOW EMA_50)")
        print("="*100)
        print(f"{'Date':<12} {'Price':>8} {'EMA_20':>8} {'EMA_50':>8} {'ADX':>6} {'Signal':>8}")
        print("-"*100)
        
        for idx, row in bearish_crosses.iterrows():
            print(f"{str(row['Date'])[:10]:<12} "
                  f"{row['Adj Close']:8.2f} "
                  f"{row['EMA_Fast']:8.2f} "
                  f"{row['EMA_Slow']:8.2f} "
                  f"{row['ADX']:6.2f} "
                  f"{'SELL':>8}")
    
    # ADX statistics
    print("\n" + "="*100)
    print("ADX STATISTICS")
    print("="*100)
    
    valid_adx = df['ADX'].dropna()
    
    print(f"Average ADX: {valid_adx.mean():.2f}")
    print(f"Median ADX: {valid_adx.median():.2f}")
    print(f"Min ADX: {valid_adx.min():.2f}")
    print(f"Max ADX: {valid_adx.max():.2f}")
    print(f"\nDays with ADX > 25: {(valid_adx > 25).sum()} ({(valid_adx > 25).sum()/len(valid_adx)*100:.1f}%)")
    print(f"Days with ADX > 20: {(valid_adx > 20).sum()} ({(valid_adx > 20).sum()/len(valid_adx)*100:.1f}%)")
    print(f"Days with ADX <= 20: {(valid_adx <= 20).sum()} ({(valid_adx <= 20).sum()/len(valid_adx)*100:.1f}%)")
    
    print("\n" + "="*100)


if __name__ == "__main__":
    # Analyze multiple stocks from our 15-stock universe
    stocks_to_analyze = [
        'BSE_NS',      # One we tested
        'SUZLON_NS',   # Highest trend quality
        'PAYTM_NS',    # Second highest
    ]
    
    for symbol in stocks_to_analyze:
        analyze_stock(symbol)
        print("\n\n")
