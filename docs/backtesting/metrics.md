Module metrics
==============

Functions
---------

`test_metrics()`
:   Test metrics calculations with sample data.

Classes
-------

`PerformanceMetrics()`
:   Calculate comprehensive performance metrics for trading strategies.
    
    All metrics are designed to give realistic assessment of strategy viability
    and psychological sustainability.

    ### Static methods

    `annual_return(total_return_pct, years)`
    :   Calculate annualized return.
        
        Args:
            total_return_pct: Total return percentage
            years: Number of years
        
        Returns:
            float: Annualized return percentage

    `avg_win_loss_ratio(closed_trades)`
    :   Calculate average win / average loss ratio.
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Win/loss ratio

    `calmar_ratio(annual_return, max_drawdown)`
    :   Calculate Calmar ratio (return / max drawdown).
        
        Measures return per unit of worst-case risk.
        
        Args:
            annual_return: Annual return percentage
            max_drawdown: Maximum drawdown percentage
        
        Returns:
            float: Calmar ratio

    `consecutive_streaks(closed_trades)`
    :   Calculate longest winning and losing streaks.
        
        CRITICAL for behavioral preparedness.
        
        Args:
            closed_trades: List of trade dictionaries (must be in chronological order)
        
        Returns:
            dict: Contains longest_win_streak and longest_loss_streak

    `drawdown_duration(equity_curve, dates)`
    :   Calculate drawdown duration metrics.
        
        Returns:
            dict: Contains longest underwater period, average recovery time, etc.

    `expectancy(closed_trades)`
    :   Calculate expectancy (expected value per trade).
        
        Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Expectancy as percentage

    `max_drawdown(equity_curve)`
    :   Calculate maximum drawdown percentage.
        
        Max drawdown = largest peak-to-trough decline
        
        Args:
            equity_curve: Array of portfolio values over time
        
        Returns:
            float: Maximum drawdown as percentage

    `monthly_win_rate(equity_curve, dates)`
    :   Calculate percentage of positive months.
        
        Easier to stomach than trade-level win rate.
        
        Args:
            equity_curve: Portfolio values over time
            dates: Corresponding dates
        
        Returns:
            float: Monthly win rate as percentage

    `profit_factor(closed_trades)`
    :   Calculate profit factor (gross profits / gross losses).
        
        Industry standard metric. PF > 1.5 is good, > 2.0 is excellent.
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Profit factor

    `sharpe_ratio(returns, risk_free_rate=0.07)`
    :   Calculate Sharpe ratio (risk-adjusted return).
        
        Sharpe = (Return - Risk Free Rate) / Standard Deviation
        
        Args:
            returns: Array of daily returns (as decimals, not percentages)
            risk_free_rate: Annual risk-free rate (default 7% for India)
        
        Returns:
            float: Annualized Sharpe ratio

    `sortino_ratio(returns, risk_free_rate=0.07)`
    :   Calculate Sortino ratio (only penalizes downside volatility).
        
        Better than Sharpe for strategies with asymmetric returns.
        
        Args:
            returns: Array of daily returns
            risk_free_rate: Annual risk-free rate
        
        Returns:
            float: Annualized Sortino ratio

    `time_in_market(portfolio_history)`
    :   Calculate average capital deployment.
        
        Args:
            portfolio_history: List of dicts with 'cash' and 'positions_value'
        
        Returns:
            float: Average percentage of capital deployed

    `total_return(initial_capital, final_capital)`
    :   Calculate total return percentage.
        
        Args:
            initial_capital: Starting portfolio value
            final_capital: Ending portfolio value
        
        Returns:
            float: Total return as percentage

    `win_rate(closed_trades)`
    :   Calculate win rate percentage.
        
        Args:
            closed_trades: List of trade dictionaries with 'profit' key
        
        Returns:
            float: Win rate as percentage

    `worst_loss(closed_trades)`
    :   Find single worst loss.
        
        Checks if stop losses are working effectively.
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Worst single loss as percentage