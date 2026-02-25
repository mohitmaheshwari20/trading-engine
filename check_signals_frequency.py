from data.loader import DataLoader
from utils.config_loader import ConfigLoader
from data.indicators import TechnicalIndicators

config_loader = ConfigLoader()
main_config = config_loader.load_config('config')
data_path = main_config['data']['source_dir']

loader = DataLoader(data_path)
stocks = loader.list_stocks()

print("Checking signal frequency across all 200 stocks (2020-2024)...\n")

total_signals = 0

for symbol in stocks[:50]:  # Check first 50
    try:
        df = loader.load_stock(symbol)
        df = df[(df['Date'] >= '2020-01-01') & (df['Date'] <= '2024-12-31')]
        
        if len(df) < 200:
            continue
        
        df = TechnicalIndicators.add_all_indicators(df)
        
        # Count days meeting all 3 conditions
        signals = df[
            (df['RSI'] < 30) & 
            (df['Adj Close'] <= df['BB_Lower']) & 
            (df['Volume_Ratio'] > 1.2)
        ]
        
        if len(signals) > 0:
            total_signals += len(signals)
            print(f"{symbol}: {len(signals)} signal days")
    
    except Exception as e:
        continue

print(f"\nTotal signal opportunities (50 stocks, 2020-2024): {total_signals}")
print(f"Average per stock: {total_signals/50:.1f} signals over 5 years")