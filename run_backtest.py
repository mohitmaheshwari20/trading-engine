import sys
from datetime import datetime

from data.loader import DataLoader
from utils.config_loader import ConfigLoader
from strategies.mean_reversion import MeanReversionStrategy
from backtesting.engine import BacktestEngine

def main():
    """
    Run backtest on mean reversion strategy.
    """
    print("="*70)
    print("SYSTEMATIC TRADING ENGINE - BACKTEST")
    print("="*70)
    print()
    
    # Load configuration
    config_loader = ConfigLoader()
    main_config = config_loader.load_config('config')
    strategy_config = config_loader.load_config('strategies_config')
    
    # Get parameters
    data_path = main_config['data']['source_dir']
    initial_capital = main_config['capital']['initial_capital']
    
    # Create strategy
    mr_config = strategy_config['mean_reversion']
    strategy = MeanReversionStrategy(mr_config)
    
    # Create data loader
    loader = DataLoader(data_path)
    stocks = loader.list_stocks()
    
    print(f"Stocks available: {len(stocks)}")
    print(f"Using first 50 stocks for faster testing...\n")
    
    # Use subset for faster testing (remove this limit for full backtest)
    stocks_to_trade = stocks[:50]
    
    # Create backtest engine
    backtest = BacktestEngine(
        strategy=strategy,
        initial_capital=initial_capital,
        start_date='2020-01-01',  # Start with 2 years for quick test
        end_date='2024-12-31',
        transaction_cost_pct=main_config['costs']['total_cost_estimate_pct'],
        debug = True # Enable debug logging for detailed output
    )
    
    # Run backtest
    results = backtest.run(loader, stocks_to_trade)
    
    if results:
        # Print results
        backtest.print_results(results)
        
        # Show some sample trades
        print("\nSAMPLE TRADES (First 10):")
        print("="*70)
        for trade in results['closed_trades'][:10]:
            print(f"{trade['symbol']:15} "
                  f"{trade['entry_date'].date()} -> {trade['exit_date'].date()} "
                  f"({trade['hold_days']:2}d) "
                  f"{trade['profit_pct']:+6.2f}% "
                  f"[{trade['exit_reason']}]")


if __name__ == "__main__":
    main()