Module engine
=============

Classes
-------

`BacktestEngine(strategy, initial_capital, start_date, end_date, transaction_cost_pct=0.009, debug=False)`
:   Event-driven backtesting engine.
    
    Supports two-stage entry signals:
        SIGNAL_WATCH (2) — adds stock to watchlist on crossover day
        SIGNAL_BUY   (1) — executes entry after Day 3 confirmation
        SIGNAL_SELL (-1) — exits position

    ### Methods

    `calculate_results(self)`
    :   Calculate and return all performance metrics.

    `check_exits(self, date)`
    :   Check all open positions for exit conditions.

    `check_watchlist_confirmations(self, date)`
    :   Check all watchlist stocks for Day 3 confirmation.
        
        For each stock on the watchlist:
            - If today is exactly 3 trading days after the crossover date:
                → Call strategy.check_confirmation()
                → If confirmed: generate BUY signal
                → Whether confirmed or not: remove from watchlist
            - If crossover is older than 3 trading days (missed window):
                → Remove from watchlist (expired)
        
        Returns:
            list: Confirmed BUY signals ready for execution

    `execute_entries(self, signals, date, max_positions=5)`
    :   Execute buy orders for confirmed signals.

    `get_trading_dates(self)`
    :   Return sorted list of all trading dates within the backtest range.

    `load_all_data(self, loader, stocks_list)`
    :   Load data and pre-calculate all indicators once.

    `print_results(self, results)`
    :   Print formatted backtest results.

    `run(self, loader, stocks_list)`
    :   Run the full backtest.

    `scan_for_signals(self, date)`
    :   Scan all stocks for WATCH signals on the current date.
        
        WATCH signals are added to the watchlist.
        BUY signals generated here (direct entry) are also supported
        for backwards compatibility with strategies that do not use
        two-stage confirmation.

`Portfolio(initial_capital, transaction_cost_pct=0.009, debug=False)`
:   Tracks cash, positions, trades, and portfolio value over time.

    ### Methods

    `buy(self, symbol, shares, price, date, stop_loss)`
    :

    `can_open_position(self, max_positions=5)`
    :

    `get_positions_value(self, date, price_data)`
    :

    `get_total_value(self, date, price_data)`
    :

    `has_cash_for_trade(self, required_amount)`
    :

    `record_equity(self, date, price_data)`
    :

    `sell(self, symbol, price, date, reason)`
    :

`Position(symbol, shares, entry_price, entry_date, stop_loss)`
:   Represents a single open position.

    ### Methods

    `get_current_value(self, current_price)`
    :

    `get_profit(self, current_price)`
    :

    `get_profit_pct(self, current_price)`
    :