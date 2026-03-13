import pandas as pd

df = pd.read_csv(r'C:\Projects\Backtesting System\data\NIFTY_NS.csv')
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values('Date').reset_index(drop=True)
df = df.rename(columns={'Adj_Close': 'Adj Close'})

df = df[(df['Date'] >= '2017-01-01') & (df['Date'] <= '2025-12-31')]

print(f"Rows in backtest window  : {len(df)}")
print(f"Date range               : {df['Date'].min().date()} to {df['Date'].max().date()}")
print(f"Missing Close values     : {df['Close'].isna().sum()}")

df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
print(f"\nEMA200 (last 3)          : {df['EMA200'].tail(3).round(2).tolist()}")
print(f"Close  (last 3)          : {df['Close'].tail(3).round(2).tolist()}")

above = (df['Close'] > df['EMA200']).sum()
below = (df['Close'] < df['EMA200']).sum()
print(f"\nDays above EMA200        : {above} ({above/len(df)*100:.1f}%)")
print(f"Days below EMA200        : {below} ({below/len(df)*100:.1f}%)")

covid = df[(df['Date'] >= '2020-03-01') & (df['Date'] <= '2020-05-31')]
below_covid = (covid['Close'] < covid['EMA200']).sum()
print(f"COVID period below EMA200: {below_covid}/{len(covid)} days (expect most)")