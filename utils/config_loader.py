import yaml
from pathlib import Path

class ConfigLoader:
    """
    Loads and validates configuration files.
    """
    
    def __init__(self, config_dir='config'):
        self.config_dir = Path(config_dir)
        
        if not self.config_dir.exists():
            raise ValueError(f"Config directory not found: {config_dir}")
    
    def load_config(self, config_name):
        """
        Load a YAML configuration file.
        
        Args:
            config_name: Name of config file (without .yaml extension)
        
        Returns:
            dict: Configuration dictionary
        """
        filepath = self.config_dir / f"{config_name}.yaml"
        
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        with open(filepath, 'r') as f:
            config = yaml.safe_load(f)
        
        return config
    
    def get_data_dir(self):
        """Get the data directory path from config."""
        config = self.load_config('config')
        return config['data']['source_dir']
    
    def get_initial_capital(self):
        """Get initial capital from config."""
        config = self.load_config('config')
        return config['capital']['initial_capital']
    
    def get_active_strategies(self):
        """Get list of enabled strategies."""
        config = self.load_config('strategies_config')
        active = [name for name, params in config.items() 
                 if params.get('enabled', False)]
        return active


# Test function
def test_config():
    print("Testing ConfigLoader...\n")
    
    loader = ConfigLoader()
    
    # Load main config
    print("Loading main config...")
    config = loader.load_config('config')
    print(f"✓ System: {config['system']['name']}")
    print(f"✓ Initial capital: Rs. {config['capital']['initial_capital']:,}")
    print(f"✓ Max position size: {config['capital']['max_position_pct']*100}%")
    print(f"✓ Transaction cost estimate: {config['costs']['total_cost_estimate_pct']*100}%")
    
    # Load strategies config
    print("\nLoading strategies config...")
    strat_config = loader.load_config('strategies_config')
    active = loader.get_active_strategies()
    print(f"✓ Active strategies: {active}")
    
    if 'mean_reversion' in active:
        mr = strat_config['mean_reversion']
        print(f"  - RSI period: {mr['rsi_period']}")
        print(f"  - RSI oversold: {mr['rsi_oversold']}")
        print(f"  - Stop loss: {mr['stop_loss_pct']*100}%")
    
    # Load universe config
    print("\nLoading universe config...")
    universe = loader.load_config('stocks_universe')
    print(f"✓ Universe: {universe['nifty200']['name']}")
    print(f"✓ Total stocks: {universe['nifty200']['total_stocks']}")
    
    print("\n✓ All config files loaded successfully!")


if __name__ == "__main__":
    test_config()