import pandas as pd
import numpy as np
from pathlib import Path

# Load trade log
trades = pd.read_csv(r'C:\Projects\trading_engine\logs\strategy1_sectorcap_trade_log.csv')
trades['entry_date'] = pd.to_datetime(trades['entry_date'])
trades['exit_date'] = pd.to_datetime(trades['exit_date'])
trades['symbol_dot'] = trades['symbol'].str.replace('_NS', '.NS', regex=False)

# Load Nifty data and calculate EMA200
nifty = pd.read_csv(r'C:\Projects\trading_engine\data\Historical Daily Data\NIFTY_NS.csv')
nifty['Date'] = pd.to_datetime(nifty['Date'])
nifty = nifty.sort_values('Date').reset_index(drop=True)
nifty['EMA200'] = nifty['Adj_Close'].ewm(span=200, adjust=False).mean()
nifty = nifty.set_index('Date')

# For each trade, check Nifty vs EMA200 on entry date
def get_macro_state(entry_date):
    available = nifty[nifty.index <= entry_date]
    if available.empty:
        return None
    row = available.iloc[-1]
    return 'OFF' if row['Adj_Close'] < row['EMA200'] else 'ON'

trades['macro_on_entry'] = trades['entry_date'].apply(get_macro_state)

# Split into macro ON vs macro OFF trades
macro_on  = trades[trades['macro_on_entry'] == 'ON']
macro_off = trades[trades['macro_on_entry'] == 'OFF']

print("MACRO FILTER IMPACT ANALYSIS")
print("=" * 60)
print(f"Total trades          : {len(trades)}")
print(f"Entered during ON     : {len(macro_on)} ({len(macro_on)/len(trades)*100:.1f}%)")
print(f"Entered during OFF    : {len(macro_off)} ({len(macro_off)/len(trades)*100:.1f}%)")
print()

for label, subset in [('MACRO ON entries', macro_on),
                       ('MACRO OFF entries', macro_off)]:
    if len(subset) == 0:
        continue
    wins  = subset[subset['profit'] > 0]
    losses = subset[subset['profit'] <= 0]
    pf = wins['profit'].sum() / abs(losses['profit'].sum()) \
         if losses['profit'].sum() != 0 else float('inf')
    print(f"{label}:")
    print(f"  Trades         : {len(subset)}")
    print(f"  Win rate       : {(subset['profit']>0).mean()*100:.1f}%")
    print(f"  Avg P&L        : {subset['profit_pct'].mean():.2f}%")
    print(f"  Total profit   : Rs.{subset['profit'].sum():,.0f}")
    print(f"  Profit factor  : {pf:.2f}")
    print()

# Year by year breakdown for OFF entries
if len(macro_off) > 0:
    print("MACRO OFF ENTRIES — YEAR BY YEAR")
    print("-" * 40)
    macro_off = macro_off.copy()
    macro_off['year'] = macro_off['entry_date'].dt.year
    for year, grp in macro_off.groupby('year'):
        print(f"  {year}: {len(grp)} trades | "
              f"WR {(grp['profit']>0).mean()*100:.0f}% | "
              f"Avg {grp['profit_pct'].mean():.2f}% | "
              f"Total Rs.{grp['profit'].sum():,.0f}")