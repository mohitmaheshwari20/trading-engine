import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.append('..')

from backtesting.metrics import PerformanceMetrics

class Position:
    """
    Represents a single open position.
    """
    def __init__(self, symbol, shares, entry_price, entry_date, stop_loss):
        self.symbol = symbol
        self.shares = shares
        self.entry_price = entry_price
        self.entry_date = entry_date
        self.stop_loss = stop_loss
        self.highest_price = entry_price  # For trailing stop (future enhancement)
    
    def get_current_value(self, current_price):
        """Get current market value of position."""
        return self.shares * current_price
    
    def get_profit(self, current_price):
        """Get unrealized profit/loss."""
        return (current_price - self.entry_price) * self.shares
    
    def get_profit_pct(self, current_price):
        """Get profit/loss as percentage."""
        return ((current_price - self.entry_price) / self.entry_price) * 100


class Portfolio:
    """
    Tracks cash, positions, trades, and portfolio value over time.
    """
    def __init__(self, initial_capital, transaction_cost_pct=0.009,debug=False):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # {symbol: Position object}
        self.closed_trades = []
        self.equity_curve = []
        self.equity_dates = []
        self.transaction_cost_pct = transaction_cost_pct
        self.total_transaction_costs = 0
        self.debug = debug
    
    def can_open_position(self, max_positions=5):
        """Check if we can open another position."""
        return len(self.positions) < max_positions
    
    def has_cash_for_trade(self, required_amount):
        """Check if we have enough cash."""
        return self.cash >= required_amount
    
    def buy(self, symbol, shares, price, date, stop_loss):
        """
        Execute a buy order.
        If position already exists, average up.
        
        Args:
            symbol: Stock symbol
            shares: Number of shares to buy
            price: Entry price
            date: Entry date
            stop_loss: Stop loss price
        """
        # Calculate cost including transaction costs
        cost_basis = shares * price
        transaction_cost = cost_basis * self.transaction_cost_pct
        total_cost = cost_basis + transaction_cost
        
        # Capture state before
        cash_before = self.cash
        num_positions_before = len(self.positions)
        
        # Deduct from cash
        self.cash -= total_cost
        self.total_transaction_costs += transaction_cost
        
        # Check if position already exists
        if symbol in self.positions:
            # Average up the existing position
            existing_position = self.positions[symbol]
            
            # Calculate new average entry price
            existing_cost = existing_position.shares * existing_position.entry_price
            new_cost = shares * price
            total_shares = existing_position.shares + shares
            average_price = (existing_cost + new_cost) / total_shares
            
            # Update existing position
            existing_position.shares = total_shares
            existing_position.entry_price = average_price
            existing_position.entry_date = date  # Update to latest entry date
            # Keep original stop loss (could also recalculate based on new average)
            
            # Debug logging
            if self.debug:
                print(f"BUY  | {date.date()} | {symbol:15} | "
                    f"Shares: {shares:4} Rs. {price:8.2f} (AVG UP: {existing_position.shares:4} shares Rs. {average_price:8.2f}) | "
                    f"Cost: Rs. {total_cost:10,.0f} (TC: Rs. {transaction_cost:6,.0f}) | "
                    f"Positions: {num_positions_before} -> {len(self.positions)} | "
                    f"Cash: Rs. {cash_before:12,.0f} -> Rs. {self.cash:12,.0f}")
        else:
            # Create new position
            self.positions[symbol] = Position(symbol, shares, price, date, stop_loss)
            
            # Debug logging
            if self.debug:
                print(f"BUY  | {date.date()} | {symbol:15} | "
                    f"Shares: {shares:4} Rs. {price:8.2f} | "
                    f"Cost: Rs. {total_cost:10,.0f} (TC: Rs. {transaction_cost:6,.0f}) | "
                    f"Positions: {num_positions_before} -> {len(self.positions)} | "
                    f"Cash: Rs. {cash_before:12,.0f} -> Rs. {self.cash:12,.0f}")
    
    def sell(self, symbol, price, date, reason):
        """
        Execute a sell order.
        
        Args:
            symbol: Stock symbol
            price: Exit price
            date: Exit date
            reason: Exit reason (for logging)
        """
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]

        
        # Calculate revenue after transaction costs
        revenue_gross = position.shares * price
        transaction_cost = revenue_gross * self.transaction_cost_pct
        revenue_net = revenue_gross - transaction_cost

        # Capture state before
        cash_before = self.cash
        num_positions_before = len(self.positions)
            
        # Add to cash
        self.cash += revenue_net
        self.total_transaction_costs += transaction_cost
        
        # Calculate profit
        # Entry cost = shares × average entry price × 1.009 (includes entry transaction cost)
        entry_cost = position.shares * position.entry_price * 1.009
        profit = revenue_net - entry_cost
        profit_pct = (profit / entry_cost) * 100

        # Debug logging
        if self.debug:
            print(f"SELL | {date.date()} | {symbol:15} | "
                f"Shares: {position.shares:4} Rs. {price:8.2f} (Entry: Rs. {position.entry_price:8.2f}) | "
                f"Revenue: Rs. {revenue_net:10,.0f} (TC: Rs. {transaction_cost:6,.0f}) | "
                f"Positions: {num_positions_before} -> {len(self.positions)} | "
                f"Cash: Rs. {cash_before:12,.0f} -> Rs. {self.cash:12,.0f} | "
                f"P&L: Rs. {profit:9,.0f} ({profit_pct:+6.2f}%)")
        
        # Record closed trade
        self.closed_trades.append({
            'symbol': symbol,
            'entry_date': position.entry_date,
            'exit_date': date,
            'entry_price': position.entry_price,
            'exit_price': price,
            'shares': position.shares,
            'profit': profit,
            'profit_pct': profit_pct,
            'hold_days': (date - position.entry_date).days,
            'exit_reason': reason
        })
        
        # Remove position
        del self.positions[symbol]
    
    def get_positions_value(self, date, price_data):
        """
        Get current market value of all positions.
        
        Args:
            date: Current date
            price_data: Dict of {symbol: DataFrame} with price history
        
        Returns:
            float: Total market value of positions
        """
        total_value = 0
        
        for symbol, position in self.positions.items():
            if symbol not in price_data:
                # Use entry price if no current data
                current_price = position.entry_price
            else:
                df = price_data[symbol]
                df_up_to_date = df[df['Date'] <= date]
                if len(df_up_to_date) > 0:
                    current_price = df_up_to_date.iloc[-1]['Adj Close']
                else:
                    current_price = position.entry_price
            
            total_value += position.get_current_value(current_price)
        
        return total_value
    
    def get_total_value(self, date, price_data):
        """Get total portfolio value (cash + positions)."""
        positions_value = self.get_positions_value(date, price_data)
        return self.cash + positions_value
    
    def record_equity(self, date, price_data):
        """Record current equity for equity curve."""
        total_value = self.get_total_value(date, price_data)
        self.equity_curve.append(total_value)
        self.equity_dates.append(date)


class BacktestEngine:
    """
    Event-driven backtesting engine.
    
    Processes historical data day-by-day to simulate realistic trading.
    """
    
    def __init__(self, strategy, initial_capital, start_date, end_date, 
                 transaction_cost_pct=0.009,debug=False):
        """
        Initialize backtest engine.
        
        Args:
            strategy: Strategy instance (e.g., MeanReversionStrategy)
            initial_capital: Starting capital
            start_date: Backtest start date (string or datetime)
            end_date: Backtest end date (string or datetime)
            transaction_cost_pct: Transaction costs per trade (default 0.9%)
        """
        self.strategy = strategy
        self.portfolio = Portfolio(initial_capital, transaction_cost_pct,debug)
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)

        # Create portfolio with debug flag
        self.portfolio = Portfolio(
            initial_capital=initial_capital,
            transaction_cost_pct=transaction_cost_pct,
            debug=debug  # Pass debug flag
        )
        
        # Cache for loaded stock data
        self.price_data = {}
        
        # Tracking
        self.signals_generated = []
        self.signals_executed = []
        self.signals_skipped = []
    
    def load_all_data(self, loader, stocks_list):
        """Load data and pre-calculate ALL indicators once."""
        print(f"Loading and pre-calculating indicators for {len(stocks_list)} stocks...")
        
        from data.indicators import TechnicalIndicators
        
        for i, symbol in enumerate(stocks_list, 1):
            try:
                df = loader.load_stock(symbol)
                
                # Pre-calculate indicators ONCE for entire history
                df = TechnicalIndicators.add_all_indicators(
                    df,
                    rsi_period=self.strategy.rsi_period,
                    bb_period=self.strategy.bb_period,
                    bb_std=self.strategy.bb_std_dev
                )
                
                if len(df) > 0:
                    self.price_data[symbol] = df
                
                if i % 10 == 0:
                    print(f"  Processed {i}/{len(stocks_list)} stocks...")
            
            except Exception as e:
                print(f"  Error loading {symbol}: {str(e)}")
                continue
        
        print(f"Loaded {len(self.price_data)} stocks\n")
    
    
    def get_trading_dates(self):
        """
        Get all unique trading dates from loaded data.
        
        Returns:
            list: Sorted list of trading dates
        """
        all_dates = set()
        
        for df in self.price_data.values():
            # Only include dates in backtest range
            dates_in_range = df[(df['Date'] >= self.start_date) & 
                            (df['Date'] <= self.end_date)]['Date'].tolist()
            all_dates.update(dates_in_range)
        
        dates = sorted(list(all_dates))
        return dates

    def scan_for_signals(self, date):
        """Optimized: Just slice pre-calculated data."""
        signals = []
        
        for symbol, df in self.price_data.items():
            try:
                # Just slice - indicators already calculated!
                df_up_to_date = df[df['Date'] <= date].copy()
                
                if len(df_up_to_date) < 200:
                    continue
                
                # NO NEED TO RECALCULATE INDICATORS!
                latest = df_up_to_date.iloc[-1]
                
                # Check filters
                if not (self.strategy.min_price <= latest['Adj Close'] <= self.strategy.max_price):
                    continue
                if latest['Volume'] < self.strategy.min_volume:
                    continue
                
                # Check signal conditions directly
                if (latest['RSI'] < self.strategy.rsi_oversold and
                    latest['Adj Close'] <= latest['BB_Lower'] and
                    latest['Volume_Ratio'] > 1.2):
                    
                    # Calculate signal strength
                    oversold_degree = (self.strategy.rsi_oversold - latest['RSI']) / self.strategy.rsi_oversold
                    band_distance = (latest['BB_Lower'] - latest['Adj Close']) / latest['BB_Lower']
                    volume_strength = min((latest['Volume_Ratio'] - 1.0), 1.0)
                    strength = (oversold_degree + band_distance * 10 + volume_strength) / 3
                    
                    signals.append({
                        'symbol': symbol,
                        'date': date,
                        'price': latest['Adj Close'],
                        'signal_strength': strength,
                        'reason': f"RSI={latest['RSI']:.1f}, BB={latest['BB_Lower']:.2f}, Vol={latest['Volume_Ratio']:.2f}x",
                        'rsi': latest['RSI'],
                        'bb_lower': latest['BB_Lower']
                    })
            
            except Exception as e:
                continue
        
        signals.sort(key=lambda x: x['signal_strength'], reverse=True)
        return signals
    
    def check_exits(self, date):
        """
        Check all open positions for exit conditions.
        
        IMPROVED: Uses intraday Low to detect stop loss hits,
        exits at stop loss price (not close) with realistic slippage.
        
        Args:
            date: Current date
        """
        positions_to_close = []
        
        for symbol, position in list(self.portfolio.positions.items()):
            if symbol not in self.price_data:
                continue
            
            df = self.price_data[symbol]
            df_up_to_date = df[df['Date'] <= date]
            
            if len(df_up_to_date) == 0:
                continue
            
            latest = df_up_to_date.iloc[-1]
            current_price = latest['Adj Close']
            
            # Exit condition 1: Stop loss hit (IMPROVED LOGIC)
            # Check if LOW of the day touched stop loss
            if latest['Low'] <= position.stop_loss:
                # Exit at stop loss price with 2% slippage
                # But if price gapped way down (low < stop), use the low
                exit_price = max(position.stop_loss * 0.98, latest['Low'])
                
                # Conservative: don't exit better than the close
                # (assumes we got filled somewhere between low and close)
                exit_price = min(exit_price, current_price)
                
                positions_to_close.append((symbol, exit_price, 'Stop Loss'))
                continue
            
            # Exit condition 2: Max holding period (30 days)
            hold_days = (date - position.entry_date).days
            if hold_days >= self.strategy.config.get('max_holding_days', 30):
                positions_to_close.append((symbol, current_price, 'Max Hold Time'))
                continue
            
            # Exit condition 3 & 4: Need indicators (RSI overbought, Upper BB)
            try:
                # Indicators already calculated in optimized version
                # Just check the latest row
                
                # Exit condition 3: RSI overbought
                if 'RSI' in latest and latest['RSI'] > self.strategy.rsi_overbought:
                    positions_to_close.append((symbol, current_price, 'RSI Overbought'))
                    continue
                
                # Exit condition 4: Price at upper BB
                if 'BB_Upper' in latest and current_price >= latest['BB_Upper']:
                    positions_to_close.append((symbol, current_price, 'Upper BB'))
                    continue
            
            except Exception as e:
                continue
        
        # Execute exits
        for symbol, price, reason in positions_to_close:
            self.portfolio.sell(symbol, price, date, reason)
    
    def execute_entries(self, signals, date, max_positions=5):
        """
        Execute buy orders for signals.
        
        Args:
            signals: List of signal dictionaries
            date: Current date
            max_positions: Maximum concurrent positions
        """
        for signal in signals:
            # Check if we can open more positions
            if not self.portfolio.can_open_position(max_positions):
                self.signals_skipped.append({**signal, 'skip_reason': 'Max positions'})
                break
            
            # Calculate position size
            portfolio_value = self.portfolio.get_total_value(date, self.price_data)
            position_size_pct = self.strategy.position_size_pct
            position_value = portfolio_value * position_size_pct
            
            # Calculate shares
            shares = int(position_value / signal['price'])
            
            if shares == 0:
                self.signals_skipped.append({**signal, 'skip_reason': 'Insufficient capital'})
                continue
            
            # Total cost including transaction costs
            total_cost = shares * signal['price'] * (1 + self.portfolio.transaction_cost_pct)
            
            # Check if we have enough cash
            if not self.portfolio.has_cash_for_trade(total_cost):
                self.signals_skipped.append({**signal, 'skip_reason': 'Insufficient cash'})
                continue
            
            # Calculate stop loss
            stop_loss = self.strategy.calculate_stop_loss(signal['price'])
            
            # Execute buy
            self.portfolio.buy(
                signal['symbol'],
                shares,
                signal['price'],
                date,
                stop_loss
            )
            
            self.signals_executed.append(signal)

    
    def run(self, loader, stocks_list):
        """
        Run the backtest.
        
        Args:
            loader: DataLoader instance
            stocks_list: List of stock symbols to trade
        
        Returns:
            dict: Backtest results with metrics
        """
        print("="*70)
        print("STARTING BACKTEST")
        print("="*70)
        print(f"Strategy: {self.strategy.get_strategy_name()}")
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Initial Capital: Rs. {self.portfolio.initial_capital:,.0f}")
        print(f"Universe: {len(stocks_list)} stocks\n")
        
        # Load all data
        self.load_all_data(loader, stocks_list)
        
        if len(self.price_data) == 0:
            print("ERROR: No data loaded!")
            return None
        
        # Get trading dates
        trading_dates = self.get_trading_dates()
        print(f"Trading days: {len(trading_dates)}")
        print(f"Processing...\n")

        print(f"First trading date: {trading_dates[0].date()}")
        print(f"Last trading date: {trading_dates[-1].date()}")
        print(f"Processing...\n")
            
        # Main backtest loop
        progress_interval = len(trading_dates) // 10
        
        for i, date in enumerate(trading_dates, 1):
            # ONLY start trading after start_date (but track portfolio from beginning)
            if date >= self.start_date:
                # 1. Check exits on existing positions
                self.check_exits(date)


                signals = self.scan_for_signals(date)
                self.signals_generated.extend(signals)
                
                if len(signals) > 0:
                    self.execute_entries(signals, date)
            
            self.portfolio.record_equity(date, self.price_data)
                     
            # Progress indicator
            if i % progress_interval == 0:
                pct_complete = (i / len(trading_dates)) * 100
                print(f"  {pct_complete:.0f}% complete ({i}/{len(trading_dates)} days)...")
     
        # Close all remaining positions at end
        print("\nClosing remaining positions...")
        for symbol in list(self.portfolio.positions.keys()):
            df = self.price_data[symbol]
            final_price = df.iloc[-1]['Adj Close']
            self.portfolio.sell(symbol, final_price, self.end_date, 'Backtest End')

        # Record final equity after all positions closed
        self.portfolio.record_equity(self.end_date, self.price_data)  # ADD THIS LINE
        
        # Calculate final metrics
        print("\nCalculating metrics...\n")
        results = self.calculate_results()

        return results
    
    def calculate_results(self):
        """
        Calculate all performance metrics.
        
        Returns:
            dict: Complete results with all metrics
        """
        initial = self.portfolio.initial_capital
        final = self.portfolio.equity_curve[-1] if self.portfolio.equity_curve else initial
        
        # Basic returns
        total_return = PerformanceMetrics.total_return(initial, final)
        years = (self.end_date - self.start_date).days / 365.25
        annual_return = PerformanceMetrics.annual_return(total_return, years)
        
        # Calculate daily returns
        equity_series = pd.Series(self.portfolio.equity_curve)
        daily_returns = equity_series.pct_change().dropna()
        
        # Risk metrics
        sharpe = PerformanceMetrics.sharpe_ratio(daily_returns.values)
        sortino = PerformanceMetrics.sortino_ratio(daily_returns.values)
        max_dd = PerformanceMetrics.max_drawdown(self.portfolio.equity_curve)
        calmar = PerformanceMetrics.calmar_ratio(annual_return, max_dd)
        
        # Drawdown duration
        dd_metrics = PerformanceMetrics.drawdown_duration(
            self.portfolio.equity_curve,
            self.portfolio.equity_dates
        )
        
        # Trade metrics
        trades = self.portfolio.closed_trades
        win_rate = PerformanceMetrics.win_rate(trades)
        profit_factor = PerformanceMetrics.profit_factor(trades)
        expectancy = PerformanceMetrics.expectancy(trades)
        wl_ratio = PerformanceMetrics.avg_win_loss_ratio(trades)
        
        # Behavioral metrics
        streaks = PerformanceMetrics.consecutive_streaks(trades)
        worst_loss = PerformanceMetrics.worst_loss(trades)
        monthly_wr = PerformanceMetrics.monthly_win_rate(
            self.portfolio.equity_curve,
            self.portfolio.equity_dates
        )
        
        # Compile results
        results = {
            'returns': {
                'initial_capital': initial,
                'final_capital': final,
                'total_return_pct': total_return,
                'annual_return_pct': annual_return,
                'transaction_costs': self.portfolio.total_transaction_costs,
                'transaction_costs_pct': (self.portfolio.total_transaction_costs / initial) * 100
            },
            'risk': {
                'sharpe_ratio': sharpe,
                'sortino_ratio': sortino,
                'max_drawdown_pct': max_dd,
                'calmar_ratio': calmar,
                'longest_dd_days': dd_metrics['longest_dd_days'],
                'avg_recovery_days': dd_metrics['avg_recovery_days'],
                'time_underwater_pct': dd_metrics['time_underwater_pct']
            },
            'trades': {
                'total_trades': len(trades),
                'win_rate_pct': win_rate,
                'profit_factor': profit_factor,
                'expectancy_pct': expectancy,
                'avg_wl_ratio': wl_ratio,
                'monthly_win_rate_pct': monthly_wr
            },
            'behavioral': {
                'longest_win_streak': streaks['longest_win_streak'],
                'longest_loss_streak': streaks['longest_loss_streak'],
                'worst_loss_pct': worst_loss
            },
            'signals': {
                'generated': len(self.signals_generated),
                'executed': len(self.signals_executed),
                'skipped': len(self.signals_skipped)
            },
            'equity_curve': self.portfolio.equity_curve,
            'equity_dates': self.portfolio.equity_dates,
            'closed_trades': trades
        }
        
        return results
    
    def print_results(self, results):
        """
        Print formatted results.
        
        Args:
            results: Results dictionary from calculate_results()
        """
        print("="*70)
        print("BACKTEST RESULTS")
        print("="*70)
        
        # Returns
        print("\nRETURNS")
        print("-"*70)
        r = results['returns']
        print(f"Initial Capital:        Rs. {r['initial_capital']:,.0f}")
        print(f"Final Capital:          Rs. {r['final_capital']:,.0f}")
        print(f"Gross Return:           +{r['total_return_pct']:.2f}% (+{r['annual_return_pct']:.2f}% annually)")
        print(f"Transaction Costs:      Rs. {r['transaction_costs']:,.0f} (-{r['transaction_costs_pct']:.2f}%)")
        
        # Risk
        print("\nRISK METRICS")
        print("-"*70)
        risk = results['risk']
        print(f"Max Drawdown:           {risk['max_drawdown_pct']:.2f}%")
        print(f"Longest Drawdown:       {risk['longest_dd_days']:.0f} days")
        print(f"Avg Recovery Time:      {risk['avg_recovery_days']:.0f} days")
        print(f"Time Underwater:        {risk['time_underwater_pct']:.1f}%")
        print(f"Sharpe Ratio:           {risk['sharpe_ratio']:.3f}")
        print(f"Sortino Ratio:          {risk['sortino_ratio']:.3f}")
        print(f"Calmar Ratio:           {risk['calmar_ratio']:.3f}")
        
        # Trades
        print("\nTRADE STATISTICS")
        print("-"*70)
        t = results['trades']
        print(f"Total Trades:           {t['total_trades']}")
        print(f"Win Rate:               {t['win_rate_pct']:.2f}%")
        print(f"Monthly Win Rate:       {t['monthly_win_rate_pct']:.2f}%")
        print(f"Profit Factor:          {t['profit_factor']:.2f}")
        print(f"Expectancy:             {t['expectancy_pct']:.2f}% per trade")
        print(f"Avg Win/Loss Ratio:     {t['avg_wl_ratio']:.2f}")
        
        # Behavioral
        print("\nBEHAVIORAL METRICS")
        print("-"*70)
        b = results['behavioral']
        print(f"Longest Win Streak:     {b['longest_win_streak']} trades")
        print(f"Longest Loss Streak:    {b['longest_loss_streak']} trades")
        print(f"Worst Single Loss:      {b['worst_loss_pct']:.2f}%")
        
        # Signals
        print("\nSIGNAL EFFICIENCY")
        print("-"*70)
        s = results['signals']
        print(f"Signals Generated:      {s['generated']}")
        print(f"Signals Executed:       {s['executed']}")
        print(f"Signals Skipped:        {s['skipped']}")
        
        print("\n" + "="*70)