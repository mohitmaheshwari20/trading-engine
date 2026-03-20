import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from backtesting.metrics import PerformanceMetrics


class Position:
    """Represents a single open position."""

    def __init__(self, symbol, shares, entry_price, entry_date, stop_loss):
        self.symbol        = symbol
        self.shares        = shares
        self.entry_price   = entry_price
        self.entry_date    = entry_date
        self.stop_loss     = stop_loss
        self.highest_price = entry_price

    def get_current_value(self, current_price):
        return self.shares * current_price

    def get_profit(self, current_price):
        return (current_price - self.entry_price) * self.shares

    def get_profit_pct(self, current_price):
        return ((current_price - self.entry_price) / self.entry_price) * 100


class Portfolio:
    """Tracks cash, positions, trades, and portfolio value over time."""

    def __init__(self, initial_capital, transaction_cost_pct=0.009, debug=False):
        self.initial_capital       = initial_capital
        self.cash                  = initial_capital
        self.positions             = {}
        self.closed_trades         = []
        self.equity_curve          = []
        self.equity_dates          = []
        self.transaction_cost_pct  = transaction_cost_pct
        self.total_transaction_costs = 0
        self.debug                 = debug

    def can_open_position(self, max_positions=5):
        return len(self.positions) < max_positions

    def has_cash_for_trade(self, required_amount):
        return self.cash >= required_amount

    def buy(self, symbol, shares, price, date, stop_loss):
        cost_basis       = shares * price
        transaction_cost = cost_basis * self.transaction_cost_pct
        total_cost       = cost_basis + transaction_cost

        cash_before          = self.cash
        num_positions_before = len(self.positions)

        self.cash                    -= total_cost
        self.total_transaction_costs += transaction_cost

        if symbol in self.positions:
            existing      = self.positions[symbol]
            existing_cost = existing.shares * existing.entry_price
            new_cost      = shares * price
            total_shares  = existing.shares + shares
            avg_price     = (existing_cost + new_cost) / total_shares

            existing.shares      = total_shares
            existing.entry_price = avg_price
            existing.entry_date  = date

            if self.debug:
                print(f"BUY  | {date.date()} | {symbol:15} | "
                      f"Shares: {shares:4} Rs. {price:8.2f} (AVG UP) | "
                      f"Cost: Rs. {total_cost:10,.0f} | "
                      f"Positions: {num_positions_before} -> {len(self.positions)} | "
                      f"Cash: Rs. {cash_before:12,.0f} -> Rs. {self.cash:12,.0f}")
        else:
            self.positions[symbol] = Position(symbol, shares, price, date, stop_loss)

            if self.debug:
                print(f"BUY  | {date.date()} | {symbol:15} | "
                      f"Shares: {shares:4} Rs. {price:8.2f} | "
                      f"Cost: Rs. {total_cost:10,.0f} (TC: Rs. {transaction_cost:6,.0f}) | "
                      f"Positions: {num_positions_before} -> {len(self.positions)} | "
                      f"Cash: Rs. {cash_before:12,.0f} -> Rs. {self.cash:12,.0f}")

    def sell(self, symbol, price, date, reason):
        if symbol not in self.positions:
            return

        position         = self.positions[symbol]
        revenue_gross    = position.shares * price
        transaction_cost = revenue_gross * self.transaction_cost_pct
        revenue_net      = revenue_gross - transaction_cost

        cash_before          = self.cash
        num_positions_before = len(self.positions)

        self.cash                    += revenue_net
        self.total_transaction_costs += transaction_cost

        entry_cost  = position.shares * position.entry_price * 1.009
        profit      = revenue_net - entry_cost
        profit_pct  = (profit / entry_cost) * 100

        if self.debug:
            print(f"SELL | {date.date()} | {symbol:15} | "
                  f"Shares: {position.shares:4} Rs. {price:8.2f} (Entry: Rs. {position.entry_price:8.2f}) | "
                  f"Revenue: Rs. {revenue_net:10,.0f} (TC: Rs. {transaction_cost:6,.0f}) | "
                  f"Positions: {num_positions_before} -> {len(self.positions)} | "
                  f"Cash: Rs. {cash_before:12,.0f} -> Rs. {self.cash:12,.0f} | "
                  f"P&L: Rs. {profit:9,.0f} ({profit_pct:+6.2f}%)")

        self.closed_trades.append({
            'symbol'     : symbol,
            'entry_date' : position.entry_date,
            'exit_date'  : date,
            'entry_price': position.entry_price,
            'exit_price' : price,
            'shares'     : position.shares,
            'profit'     : profit,
            'profit_pct' : profit_pct,
            'hold_days'  : (date - position.entry_date).days,
            'exit_reason': reason
        })

        del self.positions[symbol]

    def get_positions_value(self, date, price_data):
        total_value = 0
        for symbol, position in self.positions.items():
            if symbol not in price_data:
                current_price = position.entry_price
            else:
                df            = price_data[symbol]
                df_up_to_date = df[df['Date'] <= date]
                current_price = df_up_to_date.iloc[-1]['Adj Close'] if len(df_up_to_date) > 0 else position.entry_price
            total_value += position.get_current_value(current_price)
        return total_value

    def get_total_value(self, date, price_data):
        return self.cash + self.get_positions_value(date, price_data)

    def record_equity(self, date, price_data):
        total_value = self.get_total_value(date, price_data)
        self.equity_curve.append(total_value)
        self.equity_dates.append(date)


class BacktestEngine:
    """
    Event-driven backtesting engine.

    Supports two-stage entry signals:
        SIGNAL_WATCH (2) — adds stock to watchlist on crossover day
        SIGNAL_BUY   (1) — executes entry after Day 3 confirmation
        SIGNAL_SELL (-1) — exits position
    """

    def __init__(self, strategy, initial_capital, start_date, end_date,
                 transaction_cost_pct=0.009, debug=False, max_positions=5,
                 sector_map=None, max_positions_per_sector=2):
        self.strategy                  = strategy
        self.start_date                = pd.to_datetime(start_date)
        self.end_date                  = pd.to_datetime(end_date)
        self.debug                     = debug
        self.max_positions             = max_positions
        self.sector_map                = sector_map or {}
        self.max_positions_per_sector  = max_positions_per_sector

        self.portfolio = Portfolio(
            initial_capital=initial_capital,
            transaction_cost_pct=transaction_cost_pct,
            debug=debug
        )

        self.price_data = {}

        # Signal tracking
        self.signals_generated = []
        self.signals_executed  = []
        self.signals_skipped   = []

        # Watchlist: {symbol: {'crossover_date': date, 'crossover_adx': float,
        #                      'signal_strength': float, 'reason': str}}
        self.watchlist = {}

        # Trading dates list — populated during run()
        self._trading_dates = []

    # ──────────────────────────────────────────────────────────────────────────
    # Data loading
    # ──────────────────────────────────────────────────────────────────────────

    def load_all_data(self, loader, stocks_list):
        """Load data and pre-calculate all indicators once."""
        print(f"Loading and pre-calculating indicators for {len(stocks_list)} stocks...")

        from data.indicators import TechnicalIndicators

        for i, symbol in enumerate(stocks_list, 1):
            try:
                df = loader.load_stock(symbol)
                df = TechnicalIndicators.add_all_indicators(
                    df,
                    rsi_period=getattr(self.strategy, 'rsi_period', 14),
                    bb_period=getattr(self.strategy, 'bb_period', 20),
                    bb_std=getattr(self.strategy, 'bb_std_dev', 2),
                    ema_fast=getattr(self.strategy, 'ema_fast_period', 20),
                    ema_slow=getattr(self.strategy, 'ema_slow_period', 50),
                    adx_period=getattr(self.strategy, 'adx_period', 14)
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
        """Return sorted list of all trading dates within the backtest range."""
        all_dates = set()
        for df in self.price_data.values():
            dates_in_range = df[
                (df['Date'] >= self.start_date) & (df['Date'] <= self.end_date)
            ]['Date'].tolist()
            all_dates.update(dates_in_range)
        return sorted(list(all_dates))

    # ──────────────────────────────────────────────────────────────────────────
    # Signal scanning
    # ──────────────────────────────────────────────────────────────────────────

    def scan_for_signals(self, date):
        """
        Scan all stocks for WATCH signals on the current date.

        WATCH signals are added to the watchlist.
        BUY signals generated here (direct entry) are also supported
        for backwards compatibility with strategies that do not use
        two-stage confirmation.
        """
        buy_signals = []

        for symbol, df in self.price_data.items():
            try:
                df_up_to_date = df[df['Date'] <= date].copy()

                if len(df_up_to_date) < 200:
                    continue

                latest = df_up_to_date.iloc[-1]

                if not (self.strategy.min_price <= latest['Adj Close'] <= self.strategy.max_price):
                    continue
                if latest['Volume'] < self.strategy.min_volume:
                    continue

                # Skip if already on watchlist or already in portfolio
                if symbol in self.watchlist or symbol in self.portfolio.positions:
                    continue

                df_with_signals = self.strategy.generate_signals(df_up_to_date)
                latest_signal   = df_with_signals.iloc[-1]

                # Two-stage: WATCH signal → add to watchlist
                if latest_signal['Signal'] == self.strategy.SIGNAL_WATCH:
                    adx_at_crossover = latest_signal.get('ADX', latest['ADX'] if 'ADX' in latest else 0)
                    self.watchlist[symbol] = {
                        'crossover_date'  : date,
                        'crossover_adx'   : adx_at_crossover,
                        'signal_strength' : latest_signal['Signal_Strength'],
                        'reason'          : latest_signal['Signal_Reason']
                    }
                    self.signals_generated.append({
                        'symbol': symbol, 'date': date,
                        'price' : latest_signal['Adj Close'],
                        'type'  : 'WATCH'
                    })
                    if self.debug:
                        print(f"  WATCHLIST ADD | {date.date()} | {symbol}")

                # Direct BUY signal (strategies without confirmation stage)
                elif latest_signal['Signal'] == self.strategy.SIGNAL_BUY:
                    buy_signals.append({
                        'symbol'          : symbol,
                        'date'            : date,
                        'price'           : latest_signal['Adj Close'],
                        'signal_strength' : latest_signal['Signal_Strength'],
                        'reason'          : latest_signal['Signal_Reason']
                    })
                    self.signals_generated.append({
                        'symbol': symbol, 'date': date,
                        'price' : latest_signal['Adj Close'],
                        'type'  : 'BUY'
                    })

            except Exception as e:
                if self.debug:
                    print(f"  Error scanning {symbol}: {str(e)}")
                continue

        buy_signals.sort(key=lambda x: x['signal_strength'], reverse=True)
        return buy_signals

    def check_watchlist_confirmations(self, date):
        """
        Check all watchlist stocks for Day 3 confirmation.

        For each stock on the watchlist:
            - If today is exactly 3 trading days after the crossover date:
                → Call strategy.check_confirmation()
                → If confirmed: generate BUY signal
                → Whether confirmed or not: remove from watchlist
            - If crossover is older than 3 trading days (missed window):
                → Remove from watchlist (expired)

        Returns:
            list: Confirmed BUY signals ready for execution
        """
        confirmed_buys = []
        to_remove      = []

        for symbol, watch_entry in self.watchlist.items():
            crossover_date = watch_entry['crossover_date']

            # Calculate trading days elapsed since crossover
            trading_days_elapsed = self._count_trading_days_between(crossover_date, date)

            # Not yet Day 3 — keep waiting
            if trading_days_elapsed < 3:
                continue

            # Day 3 or beyond — evaluate confirmation (or expire)
            to_remove.append(symbol)

            if trading_days_elapsed > 3:
                # Missed the confirmation window — expire silently
                if self.debug:
                    print(f"  WATCHLIST EXPIRED | {date.date()} | {symbol} "
                          f"(crossover was {trading_days_elapsed} days ago)")
                continue

            # Exactly Day 3 — check confirmation
            if symbol not in self.price_data:
                continue

            df            = self.price_data[symbol]
            df_up_to_date = df[df['Date'] <= date].copy()

            if len(df_up_to_date) < 200:
                continue

            confirmed = self.strategy.check_confirmation(
                df_up_to_date,
                watch_entry['crossover_date'],
                watch_entry['crossover_adx']
            )

            if confirmed:
                latest = df_up_to_date.iloc[-1]
                confirmed_buys.append({
                    'symbol'          : symbol,
                    'date'            : date,
                    'price'           : latest['Adj Close'],
                    'signal_strength' : watch_entry['signal_strength'],
                    'reason'          : watch_entry['reason'] + ' | Confirmed Day 3'
                })
                if self.debug:
                    print(f"  CONFIRMED BUY | {date.date()} | {symbol} "
                          f"(crossover: {crossover_date.date()})")
            else:
                if self.debug:
                    print(f"  CONFIRMATION FAILED | {date.date()} | {symbol}")

        # Remove processed watchlist entries
        for symbol in to_remove:
            del self.watchlist[symbol]

        confirmed_buys.sort(key=lambda x: x['signal_strength'], reverse=True)
        return confirmed_buys

    def _count_trading_days_between(self, start_date, end_date):
        """
        Count the number of trading days between two dates
        using the actual trading dates loaded from price data.
        """
        if not self._trading_dates:
            return 0
        count = sum(1 for d in self._trading_dates if start_date < d <= end_date)
        return count

    # ──────────────────────────────────────────────────────────────────────────
    # Exit checking
    # ──────────────────────────────────────────────────────────────────────────

    def check_exits(self, date):
        """Check all open positions for exit conditions."""
        positions_to_close = []

        for symbol, position in list(self.portfolio.positions.items()):
            if symbol not in self.price_data:
                continue

            df            = self.price_data[symbol]
            df_up_to_date = df[df['Date'] <= date]

            if len(df_up_to_date) == 0:
                continue

            latest        = df_up_to_date.iloc[-1]
            current_price = latest['Adj Close']

            # Exit condition 1: Stop loss hit
            if latest['Low'] <= position.stop_loss:
                exit_price = max(position.stop_loss * 0.98, latest['Low'])
                exit_price = min(exit_price, current_price)
                positions_to_close.append((symbol, exit_price, 'Stop Loss'))
                continue

            # Exit condition 2: Strategy exit signal
            try:
                df_with_signals = self.strategy.generate_signals(df_up_to_date)
                latest_signal   = df_with_signals.iloc[-1]
                if latest_signal['Signal'] == self.strategy.SIGNAL_SELL:
                    reason = latest_signal.get('Signal_Reason', 'Strategy Exit')
                    positions_to_close.append((symbol, current_price, reason))
            except Exception as e:
                if self.debug:
                    print(f"  Error checking exit for {symbol}: {str(e)}")
                continue

        for symbol, price, reason in positions_to_close:
            self.portfolio.sell(symbol, price, date, reason)

    # ──────────────────────────────────────────────────────────────────────────
    # Entry execution
    # ──────────────────────────────────────────────────────────────────────────

    def execute_entries(self, signals, date, max_positions=5):
        """Execute buy orders for confirmed signals."""
        for signal in signals:
            if not self.portfolio.can_open_position(max_positions):
                self.signals_skipped.append({**signal, 'skip_reason': 'Max positions'})
                break

            # Gate: Sector cap
            if self.sector_map:
                sym_key = signal['symbol'].replace(".", "_")
                sector  = self.sector_map.get(sym_key)
                if sector is not None:
                    sector_count = sum(
                        1 for s in self.portfolio.positions
                        if self.sector_map.get(s.replace(".", "_")) == sector
                    )
                    if sector_count >= self.max_positions_per_sector:
                        self.signals_skipped.append({**signal, 'skip_reason': f'Sector cap ({sector})'})
                        if self.debug:
                            print(f"  SECTOR CAP | {date.date()} | {signal['symbol']} "
                                  f"| {sector} already has {sector_count} positions")
                        continue

            portfolio_value = self.portfolio.get_total_value(date, self.price_data)
            position_value  = portfolio_value * self.strategy.position_size_pct
            shares          = int(position_value / signal['price'])

            if shares == 0:
                self.signals_skipped.append({**signal, 'skip_reason': 'Insufficient capital'})
                continue

            total_cost = shares * signal['price'] * (1 + self.portfolio.transaction_cost_pct)

            if not self.portfolio.has_cash_for_trade(total_cost):
                self.signals_skipped.append({**signal, 'skip_reason': 'Insufficient cash'})
                continue

            stop_loss = self.strategy.calculate_stop_loss(signal['price'])

            self.portfolio.buy(signal['symbol'], shares, signal['price'], date, stop_loss)
            self.signals_executed.append(signal)

    # ──────────────────────────────────────────────────────────────────────────
    # Main run loop
    # ──────────────────────────────────────────────────────────────────────────

    def run(self, loader, stocks_list):
        """Run the full backtest."""
        print("=" * 70)
        print("STARTING BACKTEST")
        print("=" * 70)
        print(f"Strategy: {self.strategy.get_strategy_name()}")
        print(f"Period:   {self.start_date.date()} to {self.end_date.date()}")
        print(f"Capital:  Rs. {self.portfolio.initial_capital:,.0f}")
        print(f"Universe: {len(stocks_list)} stocks\n")

        self.load_all_data(loader, stocks_list)

        if len(self.price_data) == 0:
            print("ERROR: No data loaded!")
            return None

        trading_dates        = self.get_trading_dates()
        self._trading_dates  = trading_dates  # Cache for trading day counting

        print(f"Trading days:       {len(trading_dates)}")
        print(f"First trading date: {trading_dates[0].date()}")
        print(f"Last trading date:  {trading_dates[-1].date()}")
        print(f"Processing...\n")

        progress_interval = max(len(trading_dates) // 10, 1)

        for i, date in enumerate(trading_dates, 1):
            if date >= self.start_date:

                # 1. Check exits on open positions
                self.check_exits(date)

                # 2. Check watchlist for Day 3 confirmations → confirmed BUY signals
                confirmed_buys = self.check_watchlist_confirmations(date)

                # 3. Scan for new WATCH / direct BUY signals
                new_signals = self.scan_for_signals(date)

                # 4. Execute confirmed buys first, then any direct buys
                all_buys = confirmed_buys + new_signals
                if all_buys:
                    self.execute_entries(all_buys, date, self.max_positions)

            self.portfolio.record_equity(date, self.price_data)

            if i % progress_interval == 0:
                pct = (i / len(trading_dates)) * 100
                print(f"  {pct:.0f}% complete ({i}/{len(trading_dates)} days)...")

        # Close all remaining positions at end
        print("\nClosing remaining positions...")
        for symbol in list(self.portfolio.positions.keys()):
            position         = self.portfolio.positions[symbol]
            df               = self.price_data[symbol]
            df_holding       = df[df['Date'] >= position.entry_date]
            stop_loss_hit    = False
            exit_price       = None
            exit_date        = None
            exit_reason      = 'Backtest End'

            for _, row in df_holding.iterrows():
                if row['Low'] <= position.stop_loss:
                    stop_loss_hit = True
                    exit_date     = row['Date']
                    exit_price    = max(position.stop_loss * 0.98, row['Low'])
                    exit_price    = min(exit_price, row['Adj Close'])
                    exit_reason   = 'Stop Loss'
                    break

            if not stop_loss_hit:
                exit_price = df.iloc[-1]['Adj Close']
                exit_date  = self.end_date
                exit_reason = 'Backtest End'

            self.portfolio.sell(symbol, exit_price, exit_date, exit_reason)

        self.portfolio.record_equity(self.end_date, self.price_data)

        # Export trade log
        log_dir = r"C:\Projects\trading_engine\logs"
        os.makedirs(log_dir, exist_ok=True)
        if self.portfolio.closed_trades:
            trade_log = pd.DataFrame(self.portfolio.closed_trades)[
                ['symbol', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'shares', 'exit_reason']
            ]
            trade_log.to_csv(os.path.join(log_dir, 'trade_log.csv'), index=False)
            print(f"Trade log saved: {log_dir}\\trade_log.csv ({len(trade_log)} trades)")

        print("\nCalculating metrics...\n")
        return self.calculate_results()

    # ──────────────────────────────────────────────────────────────────────────
    # Results
    # ──────────────────────────────────────────────────────────────────────────

    def calculate_results(self):
        """Calculate and return all performance metrics."""
        initial = self.portfolio.initial_capital
        final   = self.portfolio.equity_curve[-1] if self.portfolio.equity_curve else initial

        total_return  = PerformanceMetrics.total_return(initial, final)
        years         = (self.end_date - self.start_date).days / 365.25
        annual_return = PerformanceMetrics.annual_return(total_return, years)

        equity_series  = pd.Series(self.portfolio.equity_curve)
        daily_returns  = equity_series.pct_change().dropna()

        sharpe   = PerformanceMetrics.sharpe_ratio(daily_returns.values)
        sortino  = PerformanceMetrics.sortino_ratio(daily_returns.values)
        max_dd   = PerformanceMetrics.max_drawdown(self.portfolio.equity_curve)
        calmar   = PerformanceMetrics.calmar_ratio(annual_return, max_dd)

        dd_metrics = PerformanceMetrics.drawdown_duration(
            self.portfolio.equity_curve, self.portfolio.equity_dates
        )

        trades       = self.portfolio.closed_trades
        win_rate     = PerformanceMetrics.win_rate(trades)
        profit_factor= PerformanceMetrics.profit_factor(trades)
        expectancy   = PerformanceMetrics.expectancy(trades)
        wl_ratio     = PerformanceMetrics.avg_win_loss_ratio(trades)
        streaks      = PerformanceMetrics.consecutive_streaks(trades)
        worst_loss   = PerformanceMetrics.worst_loss(trades)
        monthly_wr   = PerformanceMetrics.monthly_win_rate(
            self.portfolio.equity_curve, self.portfolio.equity_dates
        )

        return {
            'returns': {
                'initial_capital'      : initial,
                'final_capital'        : final,
                'total_return_pct'     : total_return,
                'annual_return_pct'    : annual_return,
                'transaction_costs'    : self.portfolio.total_transaction_costs,
                'transaction_costs_pct': (self.portfolio.total_transaction_costs / initial) * 100
            },
            'risk': {
                'sharpe_ratio'       : sharpe,
                'sortino_ratio'      : sortino,
                'max_drawdown_pct'   : max_dd,
                'calmar_ratio'       : calmar,
                'longest_dd_days'    : dd_metrics['longest_dd_days'],
                'avg_recovery_days'  : dd_metrics['avg_recovery_days'],
                'time_underwater_pct': dd_metrics['time_underwater_pct']
            },
            'trades': {
                'total_trades'       : len(trades),
                'win_rate_pct'       : win_rate,
                'profit_factor'      : profit_factor,
                'expectancy_pct'     : expectancy,
                'avg_wl_ratio'       : wl_ratio,
                'monthly_win_rate_pct': monthly_wr
            },
            'behavioral': {
                'longest_win_streak' : streaks['longest_win_streak'],
                'longest_loss_streak': streaks['longest_loss_streak'],
                'worst_loss_pct'     : worst_loss
            },
            'signals': {
                'generated': len(self.signals_generated),
                'executed' : len(self.signals_executed),
                'skipped'  : len(self.signals_skipped),
                'watchlist_peak': max(len(self.watchlist), 0)
            },
            'equity_curve' : self.portfolio.equity_curve,
            'equity_dates' : self.portfolio.equity_dates,
            'closed_trades': trades
        }

    def print_results(self, results):
        """Print formatted backtest results."""
        print("=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)

        r = results['returns']
        print("\nRETURNS")
        print("-" * 70)
        print(f"Initial Capital:        Rs. {r['initial_capital']:,.0f}")
        print(f"Final Capital:          Rs. {r['final_capital']:,.0f}")
        print(f"Gross Return:           +{r['total_return_pct']:.2f}% (+{r['annual_return_pct']:.2f}% annually)")
        print(f"Transaction Costs:      Rs. {r['transaction_costs']:,.0f} (-{r['transaction_costs_pct']:.2f}%)")

        risk = results['risk']
        print("\nRISK METRICS")
        print("-" * 70)
        print(f"Max Drawdown:           {risk['max_drawdown_pct']:.2f}%")
        print(f"Longest Drawdown:       {risk['longest_dd_days']:.0f} days")
        print(f"Avg Recovery Time:      {risk['avg_recovery_days']:.0f} days")
        print(f"Time Underwater:        {risk['time_underwater_pct']:.1f}%")
        print(f"Sharpe Ratio:           {risk['sharpe_ratio']:.3f}")
        print(f"Sortino Ratio:          {risk['sortino_ratio']:.3f}")
        print(f"Calmar Ratio:           {risk['calmar_ratio']:.3f}")

        t = results['trades']
        print("\nTRADE STATISTICS")
        print("-" * 70)
        print(f"Total Trades:           {t['total_trades']}")
        print(f"Win Rate:               {t['win_rate_pct']:.2f}%")
        print(f"Monthly Win Rate:       {t['monthly_win_rate_pct']:.2f}%")
        print(f"Profit Factor:          {t['profit_factor']:.2f}")
        print(f"Expectancy:             {t['expectancy_pct']:.2f}% per trade")
        print(f"Avg Win/Loss Ratio:     {t['avg_wl_ratio']:.2f}")

        b = results['behavioral']
        print("\nBEHAVIORAL METRICS")
        print("-" * 70)
        print(f"Longest Win Streak:     {b['longest_win_streak']} trades")
        print(f"Longest Loss Streak:    {b['longest_loss_streak']} trades")
        print(f"Worst Single Loss:      {b['worst_loss_pct']:.2f}%")

        s = results['signals']
        print("\nSIGNAL EFFICIENCY")
        print("-" * 70)
        print(f"Signals Generated:      {s['generated']}")
        print(f"Signals Executed:       {s['executed']}")
        print(f"Signals Skipped:        {s['skipped']}")

        print("\n" + "=" * 70)
