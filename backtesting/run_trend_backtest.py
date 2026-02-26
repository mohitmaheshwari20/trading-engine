import sys
import pandas as pd
from datetime import datetime
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add current directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.loader import DataLoader
from utils.config_loader import ConfigLoader
from strategies.trend_following import TrendFollowingStrategy
from engine import BacktestEngine

def main():
    """
    Run backtest on trend following strategy (15-stock universe).
    """
    print("="*70)
    print("SYSTEMATIC TRADING ENGINE - TREND FOLLOWING BACKTEST")
    print("="*70)
    print()
    
    # Load configuration
    config_loader = ConfigLoader()
    main_config = config_loader.load_config('config')
    
    # Get parameters
    data_path = main_config['data']['source_dir']
    initial_capital = main_config['capital']['initial_capital']
    
    # Create trend following strategy config
    # (Not in config files yet - using inline config)
    trend_config = {
        'name': 'Trend Following - EMA + ADX (Version 1)',
        'ema_fast_period': 20,
        'ema_slow_period': 50,
        'adx_period': 14,
        'adx_threshold': 25,
        'trailing_stop_pct': 0.15,  # 15% trailing stop
        'position_size_pct': 0.05,  # 5% per position
        'max_concurrent_positions': 5,
        'stop_loss_pct': 0.15,  # Same as trailing stop for consistency
        'min_price': 10,
        'max_price': 10000,
        'min_volume': 100000
    }
    
    print(f"Strategy: {trend_config['name']}")
    print(f"EMA Fast/Slow: {trend_config['ema_fast_period']}/{trend_config['ema_slow_period']}")
    print(f"ADX Threshold: {trend_config['adx_threshold']}")
    print(f"Trailing Stop: {trend_config['trailing_stop_pct']*100}%")
    print(f"Position Size: {trend_config['position_size_pct']*100}%")
    print(f"Max Positions: {trend_config['max_concurrent_positions']}")
    print()
    
    # Create strategy
    strategy = TrendFollowingStrategy(trend_config)
    
    # Create data loader
    loader = DataLoader(data_path)
    
    # Load 15-stock universe
    universe_file = r'C:\Projects\trading_engine\tests\trend_following_30_universe.csv'
    print(f"Loading universe from: {universe_file}")
    
    try:
        universe_df = pd.read_csv(universe_file)
        stocks_to_trade = universe_df['symbol'].tolist()
        print(f"Loaded {len(stocks_to_trade)} stocks from universe file")
    except FileNotFoundError:
        print(f"ERROR: {universe_file} not found!")
        print("Creating default 15-stock list...")
        stocks_to_trade = [
            # Energy (5)
            'SUZLON_NS', 'ATGL_NS', 'WAAREEENER_NS', 'ADANIGREEN_NS', 'CGPOWER_NS',
            # Non-energy (10)
            'PAYTM_NS', 'ADANIENT_NS', 'BSE_NS', 'MAZDOCK_NS', 'DIXON_NS',
            'KPITTECH_NS', 'KALYANKJIL_NS', 'SWIGGY_NS', 'RVNL_NS', 'APLAPOLLO_NS'
        ]
    
    print("\nUniverse stocks:")
    for i, stock in enumerate(stocks_to_trade, 1):
        print(f"  {i:2}. {stock}")
    print()
    
    # Create backtest engine
    print("="*70)
    print("BACKTEST CONFIGURATION")
    print("="*70)
    print(f"Period: 2017-01-01 to 2025-12-31 (8 years)")
    print(f"Initial Capital: Rs. {initial_capital:,.0f}")
    print(f"Transaction Costs: {main_config['costs']['total_cost_estimate_pct']*100}%")
    print(f"Universe: {len(stocks_to_trade)} stocks")
    print("="*70)
    print()
    
    backtest = BacktestEngine(
        strategy=strategy,
        initial_capital=initial_capital,
        start_date='2017-01-01',  # Full 8-year period
        end_date='2025-12-31',
        transaction_cost_pct=main_config['costs']['total_cost_estimate_pct'],
        debug=True  # Set to True for detailed trade-by-trade logging
    )
    
    # Run backtest
    print("Starting backtest...")
    print("This may take a few minutes...\n")
    
    results = backtest.run(loader, stocks_to_trade)
    
    if results:
        # Print results
        backtest.print_results(results)
        
        # Show sample trades
        print("\n" + "="*70)
        print("SAMPLE TRADES (First 20):")
        print("="*70)
        print(f"{'Symbol':<15} {'Entry':<12} {'Exit':<12} {'Days':>4} {'Profit':>7} {'Reason':<20}")
        print("-"*70)
        
        for trade in results['closed_trades']:
            print(f"{trade['symbol']:<15} "
                  f"{trade['entry_date'].date()!s:<12} "
                  f"{trade['exit_date'].date()!s:<12} "
                  f"{trade['hold_days']:4}d "
                  f"{trade['profit_pct']:+6.2f}% "
                  f"{trade['exit_reason']:<20}")
        
        # Show breakdown by exit reason
        print("\n" + "="*70)
        print("TRADE BREAKDOWN BY EXIT REASON:")
        print("="*70)
        
        exit_reasons = {}
        for trade in results['closed_trades']:
            reason = trade['exit_reason']
            if reason not in exit_reasons:
                exit_reasons[reason] = {'count': 0, 'total_profit': 0, 'wins': 0}
            exit_reasons[reason]['count'] += 1
            exit_reasons[reason]['total_profit'] += trade['profit_pct']
            if trade['profit_pct'] > 0:
                exit_reasons[reason]['wins'] += 1
        
        for reason, stats in exit_reasons.items():
            win_rate = (stats['wins'] / stats['count']) * 100 if stats['count'] > 0 else 0
            avg_profit = stats['total_profit'] / stats['count'] if stats['count'] > 0 else 0
            print(f"{reason:<25} Count: {stats['count']:3}  Win Rate: {win_rate:5.1f}%  Avg P/L: {avg_profit:+6.2f}%")
        
        print("\n" + "="*70)
        print("BACKTEST COMPLETE")
        print("="*70)
        
        # Save results to CSV (optional - commented out for console-only)
        # trades_df = pd.DataFrame(results['closed_trades'])
        # trades_df.to_csv('trend_following_backtest_trades.csv', index=False)
        # print("\nTrades saved to: trend_following_backtest_trades.csv")
    else:
        print("\nERROR: Backtest failed to produce results")


if __name__ == "__main__":
    main()
