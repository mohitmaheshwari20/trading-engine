"""
run_strategy1_sectorcap.py
Strategy 1 (EMA 20/50 + ADX + EMA200) on Nifty 200
with sector cap: max 2 concurrent positions per sector.

Sector mapping loaded from final_nifty200_sector_mapping.json.
All other parameters identical to run_trend_backtest.py.
"""

import sys
import json
import os
import pandas as pd

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir in sys.path:
    sys.path.remove(parent_dir)
sys.path.insert(0, parent_dir)

cur = os.path.abspath(os.getcwd())
if cur == os.path.abspath(os.path.dirname(__file__)):
    if '' in sys.path:
        sys.path.remove('')
    if cur in sys.path:
        sys.path.remove(cur)

from data.loader import DataLoader
from utils.config_loader import ConfigLoader
from strategies.trend_following import TrendFollowingStrategy
from engine import BacktestEngine

SECTOR_MAPPING_FILE = r'C:\Projects\trading_engine\strategies\all_weather\final_nifty200_sector_mapping.json'
SECTOR_CAP = 2


def load_sector_map():
    """Load mapping and convert SYMBOL.NS → SYMBOL_NS keys."""
    with open(SECTOR_MAPPING_FILE) as f:
        raw = json.load(f)
    return {k.replace('.', '_'): v for k, v in raw.items()}


class SectorCappedEngine(BacktestEngine):
    """
    BacktestEngine subclass that enforces a per-sector position cap.
    Sector lookup uses the converted symbol format (SYMBOL_NS).
    """

    def __init__(self, sector_map, sector_cap, **kwargs):
        super().__init__(**kwargs)
        self.sector_map = sector_map
        self.sector_cap = sector_cap
        self.sector_rejections = 0

    def _open_sector_count(self, sector):
        """Count currently open positions in the given sector."""
        return sum(
            1 for sym in self.portfolio.positions
            if self.sector_map.get(sym) == sector
        )

    def execute_entries(self, signals, date, max_positions=5):
        """Execute entries with sector cap enforcement."""
        for signal in signals:
            if not self.portfolio.can_open_position(max_positions):
                self.signals_skipped.append({**signal, 'skip_reason': 'Max positions'})
                break

            symbol = signal['symbol']
            sector = self.sector_map.get(symbol)

            # Sector cap check (skip if sector unknown — treat as uncapped)
            if sector is not None:
                if self._open_sector_count(sector) >= self.sector_cap:
                    self.signals_skipped.append({
                        **signal,
                        'skip_reason': f'Sector cap ({sector})'
                    })
                    self.sector_rejections += 1
                    continue

            portfolio_value = self.portfolio.get_total_value(date, self.price_data)
            position_value  = portfolio_value * self.strategy.position_size_pct
            shares          = int(position_value / signal['price'])

            if shares == 0:
                self.signals_skipped.append({**signal, 'skip_reason': 'Insufficient capital'})
                continue

            total_cost = shares * signal['price'] * (1 + self.portfolio.transaction_cost_pct)

            if not self.portfolio.has_cash_for_trade(total_cost):
                self.signals_skipped.append({**signal, 'skip_reason': 'Insufficient cash'})
                continue

            stop_loss = self.strategy.calculate_stop_loss(signal['price'])
            self.portfolio.buy(symbol, shares, signal['price'], date, stop_loss)
            self.signals_executed.append(signal)


def main():
    print("=" * 70)
    print("STRATEGY 1 — NIFTY 200 WITH SECTOR CAP (max 2 per sector)")
    print("=" * 70)
    print()

    sector_map = load_sector_map()
    print(f"Sector mapping loaded: {len(sector_map)} symbols")
    sectors = sorted(set(sector_map.values()))
    print(f"Sectors: {len(sectors)}")
    print()

    config_loader = ConfigLoader()
    main_config   = config_loader.load_config('config')
    data_path     = main_config['data']['source_dir']

    trend_config = {
        'name'                   : 'Trend Following - EMA + ADX (Sector Capped)',
        'ema_fast_period'        : 20,
        'ema_slow_period'        : 50,
        'adx_period'             : 14,
        'adx_threshold'          : 20,
        'trailing_stop_pct'      : 0.15,
        'position_size_pct'      : 0.05,
        'max_concurrent_positions': 10,
        'stop_loss_pct'          : 0.15,
        'min_price'              : 10,
        'max_price'              : 10000,
        'min_volume'             : 100000,
    }

    print(f"Strategy: {trend_config['name']}")
    print(f"EMA Fast/Slow: {trend_config['ema_fast_period']}/{trend_config['ema_slow_period']}")
    print(f"ADX Threshold: {trend_config['adx_threshold']}")
    print(f"Stop Loss    : {trend_config['stop_loss_pct']*100:.0f}%")
    print(f"Position Size: {trend_config['position_size_pct']*100:.0f}%")
    print(f"Max Positions: {trend_config['max_concurrent_positions']}")
    print(f"Sector Cap   : {SECTOR_CAP} per sector")
    print()

    strategy = TrendFollowingStrategy(trend_config)
    loader   = DataLoader(data_path)

    universe_file = r'C:\Projects\trading_engine\tests\nifty200_universe.csv'
    universe_df   = pd.read_csv(universe_file)
    stocks_to_trade = universe_df['symbol'].tolist()
    print(f"Universe: {len(stocks_to_trade)} stocks")

    print("=" * 70)
    print("BACKTEST CONFIGURATION")
    print("=" * 70)
    print(f"Period           : 2017-01-01 to 2025-12-31 (8 years)")
    print(f"Initial Capital  : Rs. 1,00,000")
    print(f"Transaction Costs: {main_config['costs']['total_cost_estimate_pct']*100:.1f}%")
    print(f"Universe         : {len(stocks_to_trade)} stocks")
    print(f"Sector Cap       : {SECTOR_CAP} per sector")
    print("=" * 70)
    print()

    backtest = SectorCappedEngine(
        sector_map      = sector_map,
        sector_cap      = SECTOR_CAP,
        strategy        = strategy,
        initial_capital = 100000,
        start_date      = '2017-01-01',
        end_date        = '2025-12-31',
        transaction_cost_pct = main_config['costs']['total_cost_estimate_pct'],
        debug           = False,
        max_positions   = 10,
    )

    print("Starting backtest...")
    print("This may take a few minutes...\n")
    results = backtest.run(loader, stocks_to_trade)

    if not results:
        print("\nERROR: Backtest failed to produce results")
        return

    backtest.print_results(results)
    print(f"Sector rejections  : {backtest.sector_rejections}")

    # ── Max concurrent per sector ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("MAX CONCURRENT POSITIONS PER SECTOR")
    print("=" * 70)

    trades_df = pd.DataFrame(results['closed_trades'])
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
    trades_df['exit_date']  = pd.to_datetime(trades_df['exit_date'])
    trades_df['sector']     = trades_df['symbol'].map(sector_map).fillna('Unknown')

    trading_dates = pd.date_range('2017-01-01', '2025-12-31', freq='B')
    sector_max = {}
    for sector in sorted(trades_df['sector'].unique()):
        sec_trades = trades_df[trades_df['sector'] == sector]
        max_conc = 0
        for d in trading_dates:
            d = pd.Timestamp(d)
            # exit_date exclusive: a position that exits on day d is gone before
        # that day's entry scan runs (exits processed before entries).
        conc = ((sec_trades['entry_date'] <= d) & (sec_trades['exit_date'] > d)).sum()
            if conc > max_conc:
                max_conc = conc
        sector_max[sector] = max_conc

    exceeded = False
    for sector, mx in sorted(sector_max.items(), key=lambda x: -x[1]):
        flag = ' *** EXCEEDED CAP ***' if mx > SECTOR_CAP else ''
        print(f"  {sector:<30} max concurrent: {mx}{flag}")
        if mx > SECTOR_CAP:
            exceeded = True
    print()
    if not exceeded:
        print(f"  All sectors at or below cap of {SECTOR_CAP}. ✓")
    print()

    # ── Save outputs ──────────────────────────────────────────────────────────
    log_dir = r'C:\Projects\trading_engine\logs'
    os.makedirs(log_dir, exist_ok=True)

    trades_df.to_csv(os.path.join(log_dir, 'strategy1_sectorcap_trade_log.csv'), index=False)
    print(f"Trade log saved: logs/strategy1_sectorcap_trade_log.csv ({len(trades_df)} trades)")

    equity_df = pd.DataFrame({
        'date'           : results['equity_dates'],
        'portfolio_value': results['equity_curve'],
    })
    equity_df['date'] = pd.to_datetime(equity_df['date']).dt.strftime('%Y-%m-%d')
    daily_path = os.path.join(log_dir, 'strategy1_sectorcap_daily_equity.csv')
    equity_df.to_csv(daily_path, index=False)
    print(f"Daily equity saved: logs/strategy1_sectorcap_daily_equity.csv ({len(equity_df)} days)")


if __name__ == '__main__':
    main()
