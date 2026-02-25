import sys
from data.loader import DataLoader
from utils.config_loader import ConfigLoader
from strategies.mean_reversion import MeanReversionStrategy
from data.indicators import TechnicalIndicators
import pandas as pd

def main():
    """
    Diagnose why no signals are being generated.
    """
    print("="*70)
    print("SIGNAL GENERATION DIAGNOSTIC")
    print("="*70)
    
    # Load configuration
    config_loader = ConfigLoader()
    main_config = config_loader.load_config('config')
    strategy_config = config_loader.load_config('strategies_config')
    data_path = main_config['data']['source_dir']
    
    # Create strategy
    mr_config = strategy_config['mean_reversion']
    strategy = MeanReversionStrategy(mr_config)
    
    # Load data
    loader = DataLoader(data_path)
    stocks = loader.list_stocks()[:50]
    
    print(f"\nChecking {len(stocks)} stocks for oversold conditions...\n")
    
    oversold_count = 0
    at_lower_bb_count = 0
    high_volume_count = 0
    all_conditions_count = 0
    
    # Check each stock
    for symbol in stocks:
        try:
            df = loader.load_stock(symbol)
            
            # Filter to 2022-2024
            df = df[(df['Date'] >= '2022-01-01') & (df['Date'] <= '2024-12-31')]
            
            if len(df) < 200:
                continue
            
            # Add indicators
            df = TechnicalIndicators.add_all_indicators(df)
            
            # Check conditions
            oversold = df[df['RSI'] < 30]
            at_bb = df[df['Adj Close'] <= df['BB_Lower']]
            high_vol = df[df['Volume_Ratio'] > 1.2]
            
            # All three conditions
            all_three = df[
                (df['RSI'] < 30) & 
                (df['Adj Close'] <= df['BB_Lower']) & 
                (df['Volume_Ratio'] > 1.2)
            ]
            
            if len(oversold) > 0:
                oversold_count += 1
            if len(at_bb) > 0:
                at_lower_bb_count += 1
            if len(high_vol) > 0:
                high_volume_count += 1
            if len(all_three) > 0:
                all_conditions_count += 1
                print(f"✓ {symbol}: {len(all_three)} days met all conditions")
                print(f"  Sample dates: {all_three['Date'].head(3).tolist()}")
        
        except Exception as e:
            print(f"  Error with {symbol}: {str(e)}")