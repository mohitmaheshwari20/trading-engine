import pandas as pd
import os
from pathlib import Path

class DataLoader:
    """
    Loads stock data from CSV files.
    Designed for Yahoo Finance format with Adj Close column.
    """
    
    def __init__(self, data_dir):
        """
        Args:
            data_dir: Path to directory containing CSV files
        """
        self.data_dir = Path(data_dir)
        
        if not self.data_dir.exists():
            raise ValueError(f"Data directory not found: {data_dir}")
    
    def load_stock(self, symbol):
        """
        Load data for a single stock.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE_NS')
        
        Returns:
            pandas DataFrame with columns: Date, Open, High, Low, Close, Adj Close, Volume
        """
        # Handle both formats: RELIANCE_NS or RELIANCE_NS.csv
        if not symbol.endswith('.csv'):
            symbol = f"{symbol}.csv"
        
        filepath = self.data_dir / symbol
        
        if not filepath.exists():
            raise FileNotFoundError(f"Stock file not found: {filepath}")
        
        # Load CSV
        df = pd.read_csv(filepath)
        
        # Convert Date column to datetime
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Sort by date (oldest first)
        df = df.sort_values('Date').reset_index(drop=True)
        
        # Verify required columns exist
        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        missing = [col for col in required_cols if col not in df.columns]
        
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        return df
    
    def list_stocks(self):
        """
        List all available stock symbols.
        
        Returns:
            List of stock symbols (without .csv extension)
        """
        csv_files = list(self.data_dir.glob('*.csv'))
        
        # Remove .csv extension and return
        stocks = [f.stem for f in csv_files]
        
        # Filter out index files (you can customize this)
        stocks = [s for s in stocks if not s.startswith('NIFTY') and 'INDEX' not in s.upper()]
        
        return sorted(stocks)
    
    def get_date_range(self, symbol):
        """
        Get the start and end dates for a stock.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            tuple: (start_date, end_date)
        """
        df = self.load_stock(symbol)
        return df['Date'].min(), df['Date'].max()


# Test function
def test_loader():
    """
    Test the DataLoader with your actual data.
    Replace 'YOUR_DATA_PATH' with the actual path to your CSV files.
    """
    
    # UPDATE THIS PATH
    data_path = r"C:\Projects\Backtesting System\data"  # Change this!
    
    print("Testing DataLoader...")
    print(f"Data directory: {data_path}\n")
    
    # Create loader
    loader = DataLoader(data_path)
    
    # List available stocks
    stocks = loader.list_stocks()
    print(f"Found {len(stocks)} stock files")
    print(f"First 5 stocks: {stocks[:5]}\n")
    
    # Load a single stock (RELIANCE_NS)
    if 'RELIANCE_NS' in stocks:
        print("Loading RELIANCE_NS...")
        df = loader.load_stock('RELIANCE_NS')
        
        print(f"Loaded {len(df)} rows")
        print(f"Date range: {df['Date'].min()} to {df['Date'].max()}")
        print(f"\nFirst 3 rows:")
        print(df.head(3))
        print(f"\nLast 3 rows:")
        print(df.tail(3))
        print(f"\nColumns: {list(df.columns)}")
        
        # Check for missing data
        missing = df.isnull().sum()
        if missing.any():
            print(f"\nWarning: Missing data found:")
            print(missing[missing > 0])
        else:
            print("\n✓ No missing data")
        
        print("\n✓ DataLoader test PASSED")
    else:
        print("ERROR: RELIANCE_NS not found in stock list")
        print(f"Available stocks: {stocks[:10]}")


if __name__ == "__main__":
    test_loader()