"""
Automated Parameter Sensitivity Test Runner
Runs multiple backtest configurations and saves results to organized output files.

Usage:
    python automated_tests.py --test ema          # EMA period sensitivity
    python automated_tests.py --test stoploss     # Stop loss sensitivity  
    python automated_tests.py --test walkforward  # Walk-forward analysis
    python automated_tests.py --test all          # Run everything
"""

import sys
import os
from datetime import datetime
from pathlib import Path
import subprocess
import json
from copy import deepcopy

# Import backtest components
sys.path.append('.')
from backtesting.engine import BacktestEngine
from strategies.trend_following import TrendFollowingStrategy
from backtesting.metrics import PerformanceMetrics

class AutomatedTestRunner:
    """Runs automated parameter sensitivity tests."""
    
    def __init__(self, output_dir='test_results'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Timestamp for this test run
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Base configuration (ADX 20 baseline)
        self.base_config = {
            'universe_file': 'tests/trend_following_30_universe.csv',
            'initial_capital': 750000,
            'position_size_pct': 0.05,
            'max_concurrent_positions': 5,
            'transaction_cost_pct': 0.009,
            'ema_fast_period': 20,
            'ema_slow_period': 50,
            'adx_period': 14,
            'adx_threshold': 20,
            'trailing_stop_pct': 0.15,
            'stop_loss_pct': 0.15,      # Added - same as trailing stop
            'min_price': 10,             # Added - filter stocks
            'max_price': 10000,          # Added - filter stocks
            'min_volume': 100000,        # Added - filter stocks
            'start_date': '2017-01-01',
            'end_date': '2025-12-31'
        }
    
    def run_single_backtest(self, config, test_name):
        """Run a single backtest with given configuration."""
        print(f"\n{'='*70}")
        print(f"Running: {test_name}")
        print(f"{'='*70}")
        
        # DEBUG: Print key parameters
        print(f"Config: ADX={config['adx_threshold']}, "
              f"EMA={config['ema_fast_period']}/{config['ema_slow_period']}, "
              f"SL={config['stop_loss_pct']*100}%")
        
        # Import required modules
        from data.loader import DataLoader
        from utils.config_loader import ConfigLoader
        import pandas as pd
        
        # Load main config for data path
        config_loader = ConfigLoader()
        main_config = config_loader.load_config('config')
        data_path = main_config['data']['source_dir']
        
        # Create data loader
        loader = DataLoader(data_path)
        
        # Load universe
        try:
            universe_df = pd.read_csv(config['universe_file'])
            stocks_to_trade = universe_df['symbol'].tolist()
            print(f"Loaded {len(stocks_to_trade)} stocks from {config['universe_file']}")
        except FileNotFoundError:
            print(f"ERROR: {config['universe_file']} not found!")
            return None
        
        # Create strategy with config dictionary
        strategy = TrendFollowingStrategy(config)
        
        # DEBUG: Verify strategy actually has the parameters we set
        print(f"Strategy params: ADX={strategy.adx_threshold}, "
              f"EMA={strategy.ema_fast_period}/{strategy.ema_slow_period}, "
              f"SL={strategy.trailing_stop_pct*100}%")
        
        # Create and run backtest engine (matches run_trend_backtest.py pattern)
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=config['initial_capital'],
            start_date=config['start_date'],
            end_date=config['end_date'],
            transaction_cost_pct=config['transaction_cost_pct']
        )
        
        # Run backtest
        results = engine.run(loader, stocks_to_trade)
        
        # Save detailed results to file
        self.save_results(results, test_name, config)
        
        return results
    
    def save_results(self, results, test_name, config):
        """Save backtest results to file."""
        output_file = self.output_dir / f"{test_name}.txt"
        
        with open(output_file, 'w') as f:
            f.write(f"{'='*70}\n")
            f.write(f"TEST: {test_name}\n")
            f.write(f"DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*70}\n\n")
            
            # Configuration
            f.write("CONFIGURATION\n")
            f.write("-" * 70 + "\n")
            for key, value in config.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
            
            # Performance metrics (using nested structure)
            f.write("BACKTEST RESULTS\n")
            f.write("=" * 70 + "\n\n")
            
            # Returns
            f.write("RETURNS\n")
            f.write("-" * 70 + "\n")
            r = results['returns']
            f.write(f"Initial Capital:        Rs. {r['initial_capital']:,.0f}\n")
            f.write(f"Final Capital:          Rs. {r['final_capital']:,.0f}\n")
            f.write(f"Gross Return:           {r['total_return_pct']:+.2f}% ({r['annual_return_pct']:+.2f}% annually)\n")
            f.write(f"Transaction Costs:      Rs. {r['transaction_costs']:,.0f} ({r['transaction_costs_pct']:.2f}%)\n\n")
            
            # Risk Metrics
            f.write("RISK METRICS\n")
            f.write("-" * 70 + "\n")
            risk = results['risk']
            f.write(f"Max Drawdown:           {risk['max_drawdown_pct']:.2f}%\n")
            f.write(f"Longest Drawdown:       {risk['longest_dd_days']:.0f} days\n")
            f.write(f"Avg Recovery Time:      {risk['avg_recovery_days']:.0f} days\n")
            f.write(f"Time Underwater:        {risk['time_underwater_pct']:.1f}%\n")
            f.write(f"Sharpe Ratio:           {risk['sharpe_ratio']:.3f}\n")
            f.write(f"Sortino Ratio:          {risk['sortino_ratio']:.3f}\n")
            f.write(f"Calmar Ratio:           {risk['calmar_ratio']:.3f}\n\n")
            
            # Trade Statistics
            f.write("TRADE STATISTICS\n")
            f.write("-" * 70 + "\n")
            t = results['trades']
            f.write(f"Total Trades:           {t['total_trades']}\n")
            f.write(f"Win Rate:               {t['win_rate_pct']:.2f}%\n")
            f.write(f"Monthly Win Rate:       {t['monthly_win_rate_pct']:.2f}%\n")
            f.write(f"Profit Factor:          {t['profit_factor']:.2f}\n")
            f.write(f"Expectancy:             {t['expectancy_pct']:.2f}% per trade\n")
            f.write(f"Avg Win/Loss Ratio:     {t['avg_wl_ratio']:.2f}\n\n")
            
            # Behavioral Metrics
            f.write("BEHAVIORAL METRICS\n")
            f.write("-" * 70 + "\n")
            b = results['behavioral']
            f.write(f"Longest Win Streak:     {b['longest_win_streak']} trades\n")
            f.write(f"Longest Loss Streak:    {b['longest_loss_streak']} trades\n")
            f.write(f"Worst Single Loss:      {b['worst_loss_pct']:.2f}%\n\n")
            
            # Signal Efficiency
            f.write("SIGNAL EFFICIENCY\n")
            f.write("-" * 70 + "\n")
            s = results['signals']
            f.write(f"Signals Generated:      {s['generated']}\n")
            f.write(f"Signals Executed:       {s['executed']}\n")
            f.write(f"Signals Skipped:        {s['skipped']}\n\n")
            
            f.write("=" * 70 + "\n")
        
        print(f"✓ Results saved to: {output_file}")
    
    def test_ema_sensitivity(self):
        """Test different EMA period combinations."""
        print("\n" + "="*70)
        print("EMA PERIOD SENSITIVITY TESTS")
        print("="*70)
        
        ema_configs = [
            (10, 30, "EMA_10_30_fast"),
            (15, 40, "EMA_15_40_medfast"),
            (20, 50, "EMA_20_50_baseline"),
            (30, 60, "EMA_30_60_medslow"),
            (50, 100, "EMA_50_100_slow")
        ]
        
        results_summary = []
        
        for fast, slow, name in ema_configs:
            config = deepcopy(self.base_config)
            config['ema_fast_period'] = fast
            config['ema_slow_period'] = slow
            
            test_name = f"{self.timestamp}_ema_sensitivity_{name}"
            results = self.run_single_backtest(config, test_name)
            
            results_summary.append({
                'name': f"EMA {fast}/{slow}",
                'annual_return': results['returns']['annual_return_pct'],
                'total_return': results['returns']['total_return_pct'],
                'sharpe': results['risk']['sharpe_ratio'],
                'max_dd': results['risk']['max_drawdown_pct'],
                'trades': results['trades']['total_trades'],
                'win_rate': results['trades']['win_rate_pct'],
                'profit_factor': results['trades']['profit_factor']
            })
        
        # Save comparison table
        self.save_comparison_table(results_summary, f"{self.timestamp}_ema_comparison")
        
        return results_summary
    
    def test_stoploss_sensitivity(self):
        """Test different stop loss percentages."""
        print("\n" + "="*70)
        print("STOP LOSS SENSITIVITY TESTS")
        print("="*70)
        
        stoploss_configs = [
            (0.10, "SL_10pct"),
            (0.125, "SL_12p5pct"),
            (0.15, "SL_15pct_baseline"),
            (0.175, "SL_17p5pct"),
            (0.20, "SL_20pct")
        ]
        
        results_summary = []
        
        for sl_pct, name in stoploss_configs:
            config = deepcopy(self.base_config)
            config['trailing_stop_pct'] = sl_pct
            config['stop_loss_pct'] = sl_pct 
            
            test_name = f"{self.timestamp}_stoploss_sensitivity_{name}"
            results = self.run_single_backtest(config, test_name)
            
            results_summary.append({
                'name': f"Stop Loss {sl_pct*100:.1f}%",
                'annual_return': results['returns']['annual_return_pct'],
                'total_return': results['returns']['total_return_pct'],
                'sharpe': results['risk']['sharpe_ratio'],
                'max_dd': results['risk']['max_drawdown_pct'],
                'trades': results['trades']['total_trades'],
                'win_rate': results['trades']['win_rate_pct'],
                'profit_factor': results['trades']['profit_factor'],
                'worst_loss': results['behavioral']['worst_loss_pct']
            })
        
        # Save comparison table
        self.save_comparison_table(results_summary, f"{self.timestamp}_stoploss_comparison")
        
        return results_summary
    
    def test_walkforward(self):
        """Run walk-forward analysis with rolling windows."""
        print("\n" + "="*70)
        print("WALK-FORWARD ANALYSIS")
        print("="*70)
        
        # Define rolling windows (3-year train, 1-year test)
        windows = [
            ("2017-01-01", "2019-12-31", "2020-01-01", "2020-12-31", "W1"),
            ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31", "W2"),
            ("2019-01-01", "2021-12-31", "2022-01-01", "2022-12-31", "W3"),
            ("2020-01-01", "2022-12-31", "2023-01-01", "2023-12-31", "W4"),
            ("2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31", "W5"),
            ("2022-01-01", "2024-12-31", "2025-01-01", "2025-12-31", "W6"),
        ]
        
        results_summary = []
        
        for train_start, train_end, test_start, test_end, window_name in windows:
            # Test period only
            config = deepcopy(self.base_config)
            config['start_date'] = test_start
            config['end_date'] = test_end
            
            test_name = f"{self.timestamp}_walkforward_{window_name}_test_{test_start[:4]}"
            results = self.run_single_backtest(config, test_name)
            
            results_summary.append({
                'window': window_name,
                'train_period': f"{train_start} to {train_end}",
                'test_period': f"{test_start} to {test_end}",
                'annual_return': results['returns']['annual_return_pct'],
                'total_return': results['returns']['total_return_pct'],
                'sharpe': results['risk']['sharpe_ratio'],
                'max_dd': results['risk']['max_drawdown_pct'],
                'trades': results['trades']['total_trades']
            })
        
        # Save walk-forward summary
        self.save_walkforward_summary(results_summary, f"{self.timestamp}_walkforward_summary")
        
        return results_summary
    
    def save_comparison_table(self, results_summary, filename):
        """Save comparison table as both TXT and CSV."""
        
        # TXT format
        txt_file = self.output_dir / f"{filename}.txt"
        with open(txt_file, 'w') as f:
            f.write("="*100 + "\n")
            f.write("PARAMETER SENSITIVITY COMPARISON\n")
            f.write("="*100 + "\n\n")
            
            # Header
            f.write(f"{'Configuration':<25} {'Annual':>10} {'Total':>10} {'Sharpe':>8} ")
            f.write(f"{'MaxDD':>8} {'Trades':>8} {'Win%':>8} {'PF':>8}\n")
            f.write("-"*100 + "\n")
            
            # Rows
            for r in results_summary:
                f.write(f"{r['name']:<25} ")
                f.write(f"{r['annual_return']:>9.2f}% ")
                f.write(f"{r['total_return']:>9.2f}% ")
                f.write(f"{r['sharpe']:>8.3f} ")
                f.write(f"{r['max_dd']:>7.2f}% ")
                f.write(f"{r['trades']:>8d} ")
                f.write(f"{r['win_rate']:>7.2f}% ")
                f.write(f"{r['profit_factor']:>8.2f}\n")
            
            f.write("="*100 + "\n")
        
        print(f"✓ Comparison saved to: {txt_file}")
        
        # CSV format
        csv_file = self.output_dir / f"{filename}.csv"
        with open(csv_file, 'w') as f:
            # Header
            f.write("Configuration,Annual Return,Total Return,Sharpe,Max DD,Trades,Win Rate,Profit Factor\n")
            
            # Rows
            for r in results_summary:
                f.write(f"{r['name']},")
                f.write(f"{r['annual_return']:.2f},")
                f.write(f"{r['total_return']:.2f},")
                f.write(f"{r['sharpe']:.3f},")
                f.write(f"{r['max_dd']:.2f},")
                f.write(f"{r['trades']},")
                f.write(f"{r['win_rate']:.2f},")
                f.write(f"{r['profit_factor']:.2f}\n")
        
        print(f"✓ CSV saved to: {csv_file}")
    
    def save_walkforward_summary(self, results_summary, filename):
        """Save walk-forward analysis summary."""
        txt_file = self.output_dir / f"{filename}.txt"
        
        with open(txt_file, 'w') as f:
            f.write("="*100 + "\n")
            f.write("WALK-FORWARD ANALYSIS SUMMARY\n")
            f.write("="*100 + "\n\n")
            
            # Header
            f.write(f"{'Window':<8} {'Test Period':<25} {'Annual':>10} {'Total':>10} ")
            f.write(f"{'Sharpe':>8} {'MaxDD':>8} {'Trades':>8}\n")
            f.write("-"*100 + "\n")
            
            # Rows
            total_annual = 0
            profitable_windows = 0
            
            for r in results_summary:
                f.write(f"{r['window']:<8} ")
                f.write(f"{r['test_period']:<25} ")
                f.write(f"{r['annual_return']:>9.2f}% ")
                f.write(f"{r['total_return']:>9.2f}% ")
                f.write(f"{r['sharpe']:>8.3f} ")
                f.write(f"{r['max_dd']:>7.2f}% ")
                f.write(f"{r['trades']:>8d}\n")
                
                total_annual += r['annual_return']
                if r['annual_return'] > 0:
                    profitable_windows += 1
            
            f.write("-"*100 + "\n")
            f.write(f"\nAverage Annual Return: {total_annual / len(results_summary):.2f}%\n")
            f.write(f"Profitable Windows: {profitable_windows}/{len(results_summary)} ")
            f.write(f"({profitable_windows/len(results_summary)*100:.1f}%)\n")
            f.write("="*100 + "\n")
        
        print(f"✓ Walk-forward summary saved to: {txt_file}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run automated parameter sensitivity tests')
    parser.add_argument('--test', type=str, required=True,
                      choices=['ema', 'stoploss', 'walkforward', 'all'],
                      help='Which test to run')
    parser.add_argument('--output', type=str, default='test_results',
                      help='Output directory for results')
    
    args = parser.parse_args()
    
    # Create test runner
    runner = AutomatedTestRunner(output_dir=args.output)
    
    print("\n" + "="*70)
    print("AUTOMATED PARAMETER SENSITIVITY TEST RUNNER")
    print("="*70)
    print(f"Output directory: {runner.output_dir}")
    print(f"Timestamp: {runner.timestamp}")
    print(f"Test type: {args.test}")
    print("="*70)
    
    # Run selected tests
    if args.test == 'ema' or args.test == 'all':
        runner.test_ema_sensitivity()
    
    if args.test == 'stoploss' or args.test == 'all':
        runner.test_stoploss_sensitivity()
    
    if args.test == 'walkforward' or args.test == 'all':
        runner.test_walkforward()
    
    print("\n" + "="*70)
    print("ALL TESTS COMPLETE!")
    print(f"Results saved to: {runner.output_dir}")
    print("="*70 + "\n")


if __name__ == '__main__':
    main()
