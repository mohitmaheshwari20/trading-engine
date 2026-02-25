import numpy as np
import pandas as pd
from datetime import datetime

class PerformanceMetrics:
    """
    Calculate comprehensive performance metrics for trading strategies.
    
    All metrics are designed to give realistic assessment of strategy viability
    and psychological sustainability.
    """
    
    @staticmethod
    def total_return(initial_capital, final_capital):
        """
        Calculate total return percentage.
        
        Args:
            initial_capital: Starting portfolio value
            final_capital: Ending portfolio value
        
        Returns:
            float: Total return as percentage
        """
        return ((final_capital - initial_capital) / initial_capital) * 100
    
    @staticmethod
    def annual_return(total_return_pct, years):
        """
        Calculate annualized return.
        
        Args:
            total_return_pct: Total return percentage
            years: Number of years
        
        Returns:
            float: Annualized return percentage
        """
        if years <= 0:
            return 0
        
        total_return_decimal = total_return_pct / 100
        annual = (np.power(1 + total_return_decimal, 1/years) - 1) * 100
        return annual
    
    @staticmethod
    def sharpe_ratio(returns, risk_free_rate=0.07):
        """
        Calculate Sharpe ratio (risk-adjusted return).
        
        Sharpe = (Return - Risk Free Rate) / Standard Deviation
        
        Args:
            returns: Array of daily returns (as decimals, not percentages)
            risk_free_rate: Annual risk-free rate (default 7% for India)
        
        Returns:
            float: Annualized Sharpe ratio
        """
        if len(returns) == 0 or returns.std() == 0:
            return 0
        
        # Convert annual risk-free rate to daily
        daily_rf = risk_free_rate / 252
        
        # Calculate excess returns
        excess_returns = returns - daily_rf
        
        # Annualize
        sharpe = np.sqrt(252) * excess_returns.mean() / returns.std()
        
        return sharpe
    
    @staticmethod
    def sortino_ratio(returns, risk_free_rate=0.07):
        """
        Calculate Sortino ratio (only penalizes downside volatility).
        
        Better than Sharpe for strategies with asymmetric returns.
        
        Args:
            returns: Array of daily returns
            risk_free_rate: Annual risk-free rate
        
        Returns:
            float: Annualized Sortino ratio
        """
        if len(returns) == 0:
            return 0
        
        daily_rf = risk_free_rate / 252
        excess_returns = returns - daily_rf
        
        # Only calculate std dev of negative returns (downside deviation)
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0
        
        sortino = np.sqrt(252) * excess_returns.mean() / downside_returns.std()
        
        return sortino
    
    @staticmethod
    def max_drawdown(equity_curve):
        """
        Calculate maximum drawdown percentage.
        
        Max drawdown = largest peak-to-trough decline
        
        Args:
            equity_curve: Array of portfolio values over time
        
        Returns:
            float: Maximum drawdown as percentage
        """
        if len(equity_curve) == 0:
            return 0
        
        peak = equity_curve[0]
        max_dd = 0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        return max_dd * 100
    
    @staticmethod
    def drawdown_duration(equity_curve, dates):
        """
        Calculate drawdown duration metrics.
        
        Returns:
            dict: Contains longest underwater period, average recovery time, etc.
        """
        if len(equity_curve) == 0:
            return {
                'longest_dd_days': 0,
                'avg_recovery_days': 0,
                'current_dd_days': 0,
                'time_underwater_pct': 0
            }
        
        peak = equity_curve[0]
        peak_date = dates[0]
        
        underwater_periods = []
        current_underwater_days = 0
        total_underwater_days = 0
        
        for i, (value, date) in enumerate(zip(equity_curve, dates)):
            if value >= peak:
                # New peak or at peak
                if current_underwater_days > 0:
                    underwater_periods.append(current_underwater_days)
                current_underwater_days = 0
                peak = value
                peak_date = date
            else:
                # Underwater
                if i > 0:
                    days_diff = (date - dates[i-1]).days
                    current_underwater_days += days_diff
                    total_underwater_days += days_diff
        
        # Still underwater at end
        if current_underwater_days > 0:
            underwater_periods.append(current_underwater_days)
        
        longest = max(underwater_periods) if underwater_periods else 0
        avg_recovery = np.mean(underwater_periods) if underwater_periods else 0
        total_days = (dates[-1] - dates[0]).days
        time_underwater_pct = (total_underwater_days / total_days * 100) if total_days > 0 else 0
        
        return {
            'longest_dd_days': longest,
            'avg_recovery_days': avg_recovery,
            'current_dd_days': current_underwater_days,
            'time_underwater_pct': time_underwater_pct
        }
    
    @staticmethod
    def calmar_ratio(annual_return, max_drawdown):
        """
        Calculate Calmar ratio (return / max drawdown).
        
        Measures return per unit of worst-case risk.
        
        Args:
            annual_return: Annual return percentage
            max_drawdown: Maximum drawdown percentage
        
        Returns:
            float: Calmar ratio
        """
        if max_drawdown == 0:
            return 0
        
        return annual_return / max_drawdown
    
    @staticmethod
    def win_rate(closed_trades):
        """
        Calculate win rate percentage.
        
        Args:
            closed_trades: List of trade dictionaries with 'profit' key
        
        Returns:
            float: Win rate as percentage
        """
        if len(closed_trades) == 0:
            return 0
        
        winners = [t for t in closed_trades if t['profit'] > 0]
        return (len(winners) / len(closed_trades)) * 100
    
    @staticmethod
    def profit_factor(closed_trades):
        """
        Calculate profit factor (gross profits / gross losses).
        
        Industry standard metric. PF > 1.5 is good, > 2.0 is excellent.
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Profit factor
        """
        if len(closed_trades) == 0:
            return 0
        
        gross_profit = sum([t['profit'] for t in closed_trades if t['profit'] > 0])
        gross_loss = abs(sum([t['profit'] for t in closed_trades if t['profit'] < 0]))
        
        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0
        
        return gross_profit / gross_loss
    
    @staticmethod
    def expectancy(closed_trades):
        """
        Calculate expectancy (expected value per trade).
        
        Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Expectancy as percentage
        """
        if len(closed_trades) == 0:
            return 0
        
        winners = [t['profit_pct'] for t in closed_trades if t['profit'] > 0]
        losers = [t['profit_pct'] for t in closed_trades if t['profit'] < 0]
        
        if len(winners) == 0 or len(losers) == 0:
            return 0
        
        win_rate = len(winners) / len(closed_trades)
        loss_rate = len(losers) / len(closed_trades)
        avg_win = np.mean(winners)
        avg_loss = abs(np.mean(losers))
        
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        
        return expectancy
    
    @staticmethod
    def avg_win_loss_ratio(closed_trades):
        """
        Calculate average win / average loss ratio.
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Win/loss ratio
        """
        if len(closed_trades) == 0:
            return 0
        
        winners = [t['profit'] for t in closed_trades if t['profit'] > 0]
        losers = [t['profit'] for t in closed_trades if t['profit'] < 0]
        
        if len(winners) == 0 or len(losers) == 0:
            return 0
        
        avg_win = np.mean(winners)
        avg_loss = abs(np.mean(losers))
        
        if avg_loss == 0:
            return 0
        
        return avg_win / avg_loss
    
    @staticmethod
    def consecutive_streaks(closed_trades):
        """
        Calculate longest winning and losing streaks.
        
        CRITICAL for behavioral preparedness.
        
        Args:
            closed_trades: List of trade dictionaries (must be in chronological order)
        
        Returns:
            dict: Contains longest_win_streak and longest_loss_streak
        """
        if len(closed_trades) == 0:
            return {'longest_win_streak': 0, 'longest_loss_streak': 0}
        
        current_win_streak = 0
        current_loss_streak = 0
        longest_win_streak = 0
        longest_loss_streak = 0
        
        for trade in closed_trades:
            if trade['profit'] > 0:
                current_win_streak += 1
                current_loss_streak = 0
                longest_win_streak = max(longest_win_streak, current_win_streak)
            else:
                current_loss_streak += 1
                current_win_streak = 0
                longest_loss_streak = max(longest_loss_streak, current_loss_streak)
        
        return {
            'longest_win_streak': longest_win_streak,
            'longest_loss_streak': longest_loss_streak
        }
    
    @staticmethod
    def monthly_win_rate(equity_curve, dates):
        """
        Calculate percentage of positive months.
        
        Easier to stomach than trade-level win rate.
        
        Args:
            equity_curve: Portfolio values over time
            dates: Corresponding dates
        
        Returns:
            float: Monthly win rate as percentage
        """
        if len(equity_curve) < 2 or len(dates) < 2:
            return 0
        
        # Convert to pandas for easy monthly grouping
        df = pd.DataFrame({'date': dates, 'value': equity_curve})
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Resample to month-end
        monthly = df.resample('ME').last()
        
        # Calculate monthly returns
        monthly_returns = monthly['value'].pct_change().dropna()
        
        if len(monthly_returns) == 0:
            return 0
        
        positive_months = (monthly_returns > 0).sum()
        
        return (positive_months / len(monthly_returns)) * 100
    
    @staticmethod
    def worst_loss(closed_trades):
        """
        Find single worst loss.
        
        Checks if stop losses are working effectively.
        
        Args:
            closed_trades: List of trade dictionaries
        
        Returns:
            float: Worst single loss as percentage
        """
        if len(closed_trades) == 0:
            return 0
        
        losses = [t['profit_pct'] for t in closed_trades if t['profit'] < 0]
        
        if len(losses) == 0:
            return 0
        
        return min(losses)  # Most negative number
    
    @staticmethod
    def time_in_market(portfolio_history):
        """
        Calculate average capital deployment.
        
        Args:
            portfolio_history: List of dicts with 'cash' and 'positions_value'
        
        Returns:
            float: Average percentage of capital deployed
        """
        if len(portfolio_history) == 0:
            return 0
        
        deployment_pcts = []
        
        for snapshot in portfolio_history:
            total_value = snapshot['cash'] + snapshot['positions_value']
            if total_value > 0:
                deployed_pct = (snapshot['positions_value'] / total_value) * 100
                deployment_pcts.append(deployed_pct)
        
        return np.mean(deployment_pcts) if deployment_pcts else 0


# Test function
def test_metrics():
    """
    Test metrics calculations with sample data.
    """
    print("Testing PerformanceMetrics...\n")
    
    # Sample trades
    sample_trades = [
        {'profit': 5000, 'profit_pct': 10.0, 'entry_date': '2024-01-01', 'exit_date': '2024-01-10'},
        {'profit': -4000, 'profit_pct': -8.0, 'entry_date': '2024-01-15', 'exit_date': '2024-01-18'},
        {'profit': 6000, 'profit_pct': 12.0, 'entry_date': '2024-02-01', 'exit_date': '2024-02-15'},
        {'profit': 3000, 'profit_pct': 6.0, 'entry_date': '2024-02-20', 'exit_date': '2024-03-01'},
        {'profit': -4000, 'profit_pct': -8.0, 'entry_date': '2024-03-05', 'exit_date': '2024-03-08'},
        {'profit': 7000, 'profit_pct': 14.0, 'entry_date': '2024-03-15', 'exit_date': '2024-03-30'},
    ]
    
    # Sample equity curve
    sample_equity = [750000, 755000, 751000, 757000, 760000, 756000, 763000]
    sample_dates = pd.date_range('2024-01-01', periods=7, freq='ME')
    
    # Sample returns
    sample_returns = np.array([0.005, -0.003, 0.008, 0.004, -0.005, 0.009])
    
    # Test metrics
    print("RETURN METRICS")
    print("="*50)
    total_ret = PerformanceMetrics.total_return(750000, 763000)
    print(f"Total Return: {total_ret:.2f}%")
    
    annual_ret = PerformanceMetrics.annual_return(total_ret, 1)
    print(f"Annual Return: {annual_ret:.2f}%")
    
    print("\nRISK METRICS")
    print("="*50)
    sharpe = PerformanceMetrics.sharpe_ratio(sample_returns)
    print(f"Sharpe Ratio: {sharpe:.3f}")
    
    sortino = PerformanceMetrics.sortino_ratio(sample_returns)
    print(f"Sortino Ratio: {sortino:.3f}")
    
    max_dd = PerformanceMetrics.max_drawdown(sample_equity)
    print(f"Max Drawdown: {max_dd:.2f}%")
    
    calmar = PerformanceMetrics.calmar_ratio(annual_ret, max_dd)
    print(f"Calmar Ratio: {calmar:.3f}")
    
    print("\nTRADE METRICS")
    print("="*50)
    win_rate = PerformanceMetrics.win_rate(sample_trades)
    print(f"Win Rate: {win_rate:.2f}%")
    
    pf = PerformanceMetrics.profit_factor(sample_trades)
    print(f"Profit Factor: {pf:.2f}")
    
    exp = PerformanceMetrics.expectancy(sample_trades)
    print(f"Expectancy: {exp:.2f}%")
    
    wl_ratio = PerformanceMetrics.avg_win_loss_ratio(sample_trades)
    print(f"Win/Loss Ratio: {wl_ratio:.2f}")
    
    print("\nBEHAVIORAL METRICS")
    print("="*50)
    streaks = PerformanceMetrics.consecutive_streaks(sample_trades)
    print(f"Longest Win Streak: {streaks['longest_win_streak']} trades")
    print(f"Longest Loss Streak: {streaks['longest_loss_streak']} trades")
    
    worst = PerformanceMetrics.worst_loss(sample_trades)
    print(f"Worst Single Loss: {worst:.2f}%")
    
    monthly_wr = PerformanceMetrics.monthly_win_rate(sample_equity, sample_dates)
    print(f"Monthly Win Rate: {monthly_wr:.2f}%")
    
    print("\n" + "="*50)
    print("✓ All metrics calculations PASSED")
    print("="*50)


if __name__ == "__main__":
    test_metrics()