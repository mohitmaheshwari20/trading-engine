import sys
from datetime import datetime
from data.loader import DataLoader
from utils.config_loader import ConfigLoader
from strategies.mean_reversion import MeanReversionStrategy
from data.indicators import TechnicalIndicators
import pandas as pd

def main():
    print("="*70)
    print("BACKTEST DEBUG")
    print("="*70)
    
    # Load configuration
    config_loader = ConfigLoader()
    main_config = config_loader.load_config('config')
    strategy_config = config_loader.load_config('strategies_config')
    data_path = main_config['data']['source_dir']
    
    # Create strategy
    mr_config = strategy_config['mean_reversion']
    strategy = MeanReversionStrategy(mr_config)
    
    print(f"\nStrategy filters:")
    print(f"  Min price: Rs. {strategy.min_price}")
    print(f"  Max price: Rs. {strategy.max_price}")
    print(f"  Min volume: {strategy.min_volume:,}")
    
    # Load data
    loader = DataLoader(data_path)
    stocks = loader.list_stocks()[:5]  # Just 5 stocks for debugging
    
    print(f"\nTesting with {len(stocks)} stocks: {stocks}")
    
    # Load and test each stock
    for symbol in stocks:
        print(f"\n{'='*70}")
        print(f"TESTING: {symbol}")
        print(f"{'='*70}")
        
        try:
            df = loader.load_stock(symbol)
            
            # Filter to date range
            df = df[(df['Date'] >= '2020-09-01') & (df['Date'] <= '2024-12-31')]
            
            print(f"Rows in date range: {len(df)}")
            
            if len(df) < 200:
                print("❌ Not enough data (< 200 rows)")
                continue
            
            # Check latest price and volume
            latest = df.iloc[-1]
            print(f"\nLatest data ({latest['Date'].date()}):")
            print(f"  Price: Rs. {latest['Adj Close']:.2f}")
            print(f"  Volume: {latest['Volume']:,.0f}")
            
            # Check filters
            passes_price = strategy.min_price <= latest['Adj Close'] <= strategy.max_price
            passes_volume = latest['Volume'] >= strategy.min_volume
            
            print(f"\nFilter checks:")
            print(f"  Price in range [{strategy.min_price}, {strategy.max_price}]: {passes_price}")
            print(f"  Volume >= {strategy.min_volume:,}: {passes_volume}")
            
            if not (passes_price and passes_volume):
                print("❌ Failed filters")
                continue
            
            # Add indicators
            print("\nAdding indicators...")
            df = TechnicalIndicators.add_all_indicators(df)
            
            # Check for signals
            print("Checking for signals...")
            
            signals = df[
                (df['RSI'] < 30) & 
                (df['Adj Close'] <= df['BB_Lower']) & 
                (df['Volume_Ratio'] > 1.2)
            ]
            
            print(f"Signal days found: {len(signals)}")
            
            if len(signals) > 0:
                print(f"\n✓ SIGNALS FOUND!")
                print(f"First 3 signal dates:")
                for idx, row in signals.head(3).iterrows():
                    print(f"  {row['Date'].date()}: RSI={row['RSI']:.1f}, "
                          f"Price={row['Adj Close']:.2f}, BB_Lower={row['BB_Lower']:.2f}, "
                          f"Vol={row['Volume_Ratio']:.2f}x")
                
                # Now test strategy.generate_signals() on one signal date
                signal_date = signals.iloc[0]['Date']
                print(f"\nTesting strategy.generate_signals() on {signal_date.date()}...")
                
                df_up_to_signal = df[df['Date'] <= signal_date].copy()
                df_with_strategy_signals = strategy.generate_signals(df_up_to_signal)
                
                latest_signal = df_with_strategy_signals.iloc[-1]
                print(f"  Strategy Signal: {latest_signal['Signal']}")
                print(f"  Strategy Strength: {latest_signal['Signal_Strength']:.3f}")
                print(f"  Strategy Reason: {latest_signal['Signal_Reason']}")
                
                if latest_signal['Signal'] != 1:
                    print("  ⚠ WARNING: Manual check found signal but strategy didn't!")
            else:
                print("❌ No signals found")
        
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()