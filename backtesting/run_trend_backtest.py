import sys
import json
import pandas as pd
from datetime import datetime
import os

# Add parent directory to path for imports (so `backtesting` package is discoverable)
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir in sys.path:
    sys.path.remove(parent_dir)
sys.path.insert(0, parent_dir)

# Remove current directory entry when it's the package itself, to avoid
# shadowing `backtesting` package when script is executed from inside it.
cur = os.path.abspath(os.getcwd())
if cur == os.path.abspath(os.path.dirname(__file__)):
    if '' in sys.path:
        sys.path.remove('')
    if cur in sys.path:
        sys.path.remove(cur)

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
        'adx_threshold': 20,
        'trailing_stop_pct': 0.15,  # 15% trailing stop
        'position_size_pct': 0.05,  # 5% per position
        'max_concurrent_positions': 10,
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
    universe_file = r'C:\Projects\trading_engine\tests\nifty200_universe.csv'
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
    
    # Load sector map (RELIANCE.NS → RELIANCE_NS key format)
    sector_map_file = r'C:\Projects\trading_engine\strategies\all_weather\final_nifty200_sector_mapping.json'
    with open(sector_map_file, 'r') as f:
        raw_sector_map = json.load(f)
    sector_map = {k.replace('.', '_'): v for k, v in raw_sector_map.items()}
    print(f"Sector map loaded: {len(sector_map)} symbols across "
          f"{len(set(sector_map.values()))} sectors")
    print(f"Sector cap: max 2 positions per sector")
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
        initial_capital=100000,
        start_date='2023-01-01',  # Full 8-year period
        end_date='2025-12-31',
        transaction_cost_pct=main_config['costs']['total_cost_estimate_pct'],
        debug=False,
        max_positions=10,
        sector_map=sector_map,
        max_positions_per_sector=2
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
        
        import os
        log_dir = r'C:\Projects\trading_engine\logs'
        os.makedirs(log_dir, exist_ok=True)

        # Save trade log
        trades_df = pd.DataFrame(results['closed_trades'])
        trade_log_path = os.path.join(log_dir, 'strategy1_nifty200_trade_log.csv')
        trades_df.to_csv(trade_log_path, index=False)
        print(f"\nTrade log saved: {trade_log_path} ({len(trades_df)} trades)")

        # Save monthly equity curve
        equity_df = pd.DataFrame({
            'date'           : results['equity_dates'],
            'portfolio_value': results['equity_curve']
        })
        equity_df['date'] = pd.to_datetime(equity_df['date'])
        equity_df = equity_df.set_index('date')
        monthly_equity = equity_df['portfolio_value'].resample('ME').last().reset_index()
        monthly_equity.columns = ['date', 'portfolio_value']
        monthly_equity['date'] = monthly_equity['date'].dt.strftime('%Y-%m-%d')
        monthly_path = os.path.join(log_dir, 'strategy1_monthly_equity.csv')
        monthly_equity.to_csv(monthly_path, index=False)
        print(f"Monthly equity curve saved: {monthly_path} ({len(monthly_equity)} months)")

        # Save daily equity curve
        daily_equity = equity_df['portfolio_value'].reset_index()
        daily_equity.columns = ['date', 'portfolio_value']
        daily_equity['date'] = pd.to_datetime(daily_equity['date']).dt.strftime('%Y-%m-%d')
        daily_path = os.path.join(log_dir, 'strategy1_nifty200_daily_equity.csv')
        daily_equity.to_csv(daily_path, index=False)
        print(f"Daily equity curve saved: {daily_path} ({len(daily_equity)} days)")
    else:
        print("\nERROR: Backtest failed to produce results")


if __name__ == "__main__":
    main()
