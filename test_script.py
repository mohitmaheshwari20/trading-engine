import pandas as pd

df = pd.read_csv(r'C:\Projects\trading_engine\logs\all_weather_p63_trade_log.csv')

print("POSITION SIZING SANITY CHECK")
print(f"Avg shares per trade : {df['shares'].mean():.1f}")
print(f"Min shares           : {df['shares'].min()}")
print(f"Max shares           : {df['shares'].max()}")
print(f"Trades with <=2 shares: {(df['shares'] <= 2).sum()} ({(df['shares'] <= 2).mean()*100:.1f}%)")
print(f"Trades with <=4 shares: {(df['shares'] <= 4).sum()} ({(df['shares'] <= 4).mean()*100:.1f}%)")