from backtesting.engine import Portfolio, Position
from datetime import datetime

print("="*70)
print("TESTING PORTFOLIO BUY/SELL MATH")
print("="*70)

# Create portfolio
portfolio = Portfolio(initial_capital=750000, transaction_cost_pct=0.009)

print(f"\nInitial capital: Rs. {portfolio.cash:,.0f}")

# TEST 1: Single buy-sell cycle
print("\n" + "-"*70)
print("TEST 1: Buy and sell 1 stock")
print("-"*70)

date = datetime(2021, 1, 1)

# Buy 10 shares at Rs. 1000
shares = 10
price = 1000
stop_loss = 920

print(f"\nBUYING: {shares} shares @ Rs. {price}")
expected_cost = shares * price * 1.009
print(f"Expected cost: Rs. {expected_cost:,.2f}")

cash_before = portfolio.cash
portfolio.buy('TEST1', shares, price, date, stop_loss)
cash_after = portfolio.cash

print(f"Cash before: Rs. {cash_before:,.0f}")
print(f"Cash after: Rs. {cash_after:,.0f}")
print(f"Actual cost: Rs. {cash_before - cash_after:,.2f}")
print(f"Difference: Rs. {(cash_before - cash_after) - expected_cost:.2f}")

if abs((cash_before - cash_after) - expected_cost) < 0.01:
    print("✓ BUY math is correct")
else:
    print("✗ BUY math is WRONG!")

# Sell at profit
sell_price = 1100

print(f"\nSELLING: {shares} shares @ Rs. {sell_price}")
expected_revenue = shares * sell_price * 0.991
print(f"Expected revenue: Rs. {expected_revenue:,.2f}")

cash_before = portfolio.cash
portfolio.sell('TEST1', sell_price, date, 'Test')
cash_after = portfolio.cash

print(f"Cash before: Rs. {cash_before:,.0f}")
print(f"Cash after: Rs. {cash_after:,.0f}")
print(f"Actual revenue: Rs. {cash_after - cash_before:,.2f}")
print(f"Difference: Rs. {(cash_after - cash_before) - expected_revenue:.2f}")

if abs((cash_after - cash_before) - expected_revenue) < 0.01:
    print("✓ SELL math is correct")
else:
    print("✗ SELL math is WRONG!")

# Net result
print(f"\n{'='*70}")
print("NET RESULT:")
print(f"{'='*70}")
print(f"Starting cash: Rs. 750,000")
print(f"Ending cash: Rs. {portfolio.cash:,.0f}")
print(f"Change: Rs. {portfolio.cash - 750000:,.0f}")

entry_cost = shares * price * 1.009
exit_revenue = shares * sell_price * 0.991
expected_profit = exit_revenue - entry_cost

print(f"\nExpected profit: Rs. {expected_profit:,.2f}")
print(f"Actual profit: Rs. {portfolio.cash - 750000:,.0f}")
print(f"Difference: Rs. {(portfolio.cash - 750000) - expected_profit:.2f}")

if abs((portfolio.cash - 750000) - expected_profit) < 0.01:
    print("\n✓✓✓ PORTFOLIO MATH IS CORRECT ✓✓✓")
else:
    print("\n✗✗✗ PORTFOLIO MATH IS BROKEN ✗✗✗")

# TEST 2: Multiple sequential trades
print("\n" + "="*70)
print("TEST 2: Multiple sequential trades")
print("="*70)

portfolio2 = Portfolio(initial_capital=750000, transaction_cost_pct=0.009)

trades = [
    ('STOCK1', 10, 1000, 1100),  # Buy 10 @ 1000, sell @ 1100
    ('STOCK2', 20, 500, 550),    # Buy 20 @ 500, sell @ 550
    ('STOCK3', 5, 2000, 1900),   # Buy 5 @ 2000, sell @ 1900 (loss)
]

expected_cash = 750000

for symbol, shares, buy_price, sell_price in trades:
    # Buy
    portfolio2.buy(symbol, shares, buy_price, date, buy_price * 0.92)
    expected_cash -= shares * buy_price * 1.009
    
    # Sell
    portfolio2.sell(symbol, sell_price, date, 'Test')
    expected_cash += shares * sell_price * 0.991

print(f"Expected final cash: Rs. {expected_cash:,.2f}")
print(f"Actual final cash: Rs. {portfolio2.cash:,.2f}")
print(f"Difference: Rs. {portfolio2.cash - expected_cash:.2f}")

if abs(portfolio2.cash - expected_cash) < 0.01:
    print("\n✓✓✓ MULTIPLE TRADES MATH IS CORRECT ✓✓✓")
else:
    print("\n✗✗✗ MULTIPLE TRADES MATH IS BROKEN ✗✗✗")

print("\n" + "="*70)
print("TRANSACTION COSTS TRACKING:")
print("="*70)
print(f"Total transaction costs tracked: Rs. {portfolio2.total_transaction_costs:,.2f}")

expected_tc = 0
for symbol, shares, buy_price, sell_price in trades:
    expected_tc += shares * buy_price * 0.009  # Buy cost
    expected_tc += shares * sell_price * 0.009  # Sell cost

print(f"Expected transaction costs: Rs. {expected_tc:,.2f}")
print(f"Difference: Rs. {portfolio2.total_transaction_costs - expected_tc:.2f}")