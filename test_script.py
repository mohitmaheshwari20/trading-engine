import pandas as pd
from pathlib import Path

DATA_DIR = Path(r"C:\Projects\Backtesting System\data")

import json
with open(r"C:\Projects\trading_engine\strategies\all_weather\final_nifty200_sector_mapping.json") as f:
    symbols = list(json.load(f).keys())

cutoff = '2016-12-31'
start  = '2015-01-01'
eligible = []

for symbol in symbols:
    filename = symbol.replace('.', '_')
    filepath = DATA_DIR / f"{filename}.csv"
    if not filepath.exists():
        continue
    df = pd.read_csv(filepath, usecols=['Date'])
    df['Date'] = pd.to_datetime(df['Date'])
    if df['Date'].min() <= pd.Timestamp(start) and df['Date'].max() >= pd.Timestamp(cutoff):
        eligible.append(symbol)

print(f"Symbols with full 2015-2016 data : {len(eligible)}")
print(f"Out of total                      : {len(symbols)}")