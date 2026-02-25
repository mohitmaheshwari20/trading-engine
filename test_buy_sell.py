from backtesting.engine import Portfolio

# Test with 1 trade
portfolio = Portfolio(initial_capital=750000, transaction_cost_pct=0.009)

print(f"Initial cash: Rs. {portfolio.cash:,.0f}")

# Buy 10 shares at Rs. 1000
portfolio.buy('TEST', 10, 1000, date, stop_loss)
print(f"After buy: Rs. {portfolio.cash:,.0f}")
print(f"  Expected: Rs. {750000 - (10 * 1000 * 1.009):,.0f}")

# Sell 10 shares at Rs. 1100  
portfolio.sell('TEST', 1100, date, 'Test')
print(f"After sell: Rs. {portfolio.cash:,.0f}")
print(f"  Expected: Rs. {750000 - (10 * 1000 * 1.009) + (10 * 1100 * 0.991):,.0f}")