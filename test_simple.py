from data.loader import DataLoader
from utils.config_loader import ConfigLoader

print("Starting simple test...")

# Load config
config_loader = ConfigLoader()
main_config = config_loader.load_config('config')
data_path = main_config['data']['source_dir']

print(f"Data path: {data_path}")

# Load data
loader = DataLoader(data_path)
stocks = loader.list_stocks()

print(f"Total stocks: {len(stocks)}")
print(f"First 5 stocks: {stocks[:5]}")

# Load one stock
symbol = stocks[0]
print(f"\nLoading {symbol}...")

df = loader.load_stock(symbol)
print(f"Loaded {len(df)} rows")

# Filter to 2022-2024
df_filtered = df[(df['Date'] >= '2022-01-01') & (df['Date'] <= '2024-12-31')]
print(f"2022-2024 data: {len(df_filtered)} rows")

# Add indicators
from data.indicators import TechnicalIndicators
print("\nAdding indicators...")
df_with_ind = TechnicalIndicators.add_all_indicators(df_filtered)

print(f"RSI range: {df_with_ind['RSI'].min():.2f} to {df_with_ind['RSI'].max():.2f}")
print(f"RSI < 30 days: {(df_with_ind['RSI'] < 30).sum()}")

print("\n✓ Test complete!")