from data.loader import DataLoader
from utils.config_loader import ConfigLoader
import pandas as pd

config_loader = ConfigLoader()
data_path = config_loader.get_data_dir()
loader = DataLoader(data_path)

# Check one of the failed trades
symbol = 'BANKBARODA_NS'
df = loader.load_stock(symbol)

# Entry: 2020-03-02, Exit: 2020-03-12
entry_date = '2020-03-02'
exit_date = '2020-03-12'

trade_period = df[(df['Date'] >= entry_date) & (df['Date'] <= exit_date)]

print(f"BANKBARODA trade analysis:")
print(f"Entry date: {entry_date}")
print(f"Exit date: {exit_date}")
print(f"\nDaily prices during trade:")
print(trade_period[['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close']])

entry_price = trade_period.iloc[0]['Adj Close']
stop_loss = entry_price * 0.92  # 8% stop
print(f"\nEntry price: {entry_price:.2f}")
print(f"Stop loss: {stop_loss:.2f}")

# Check if any day OPENED below stop loss (gap down)
gap_downs = trade_period[trade_period['Open'] < stop_loss]
if len(gap_downs) > 0:
    print(f"\n⚠ GAP DOWNS DETECTED:")
    print(gap_downs[['Date', 'Open', 'Low']])
    print(f"\nThis explains why stop loss failed - market gapped down past stop!")