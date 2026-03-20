"""
visualize_equity.py — Equity Curve & Drawdown Analyser
Works with any daily equity CSV produced by run_trend_backtest.py

Usage:
    python visualize_equity.py --equity logs/strategy1_nifty200_daily_equity.csv
                               --title "Strategy 1 — Nifty 200 2017-2025"

    python visualize_equity.py --title "Window 1 — 2019-2020"

Optional:
    --trades logs/strategy1_sectorcap_trade_log.csv   (overlays trade markers)
    --benchmark data/NIFTY_NS.csv                     (overlays Nifty index)
"""

import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — edit defaults here
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_EQUITY    = r"C:\Projects\trading_engine\logs\strategy1_nifty200_daily_equity.csv"
DEFAULT_TRADES    = r"C:\Projects\trading_engine\logs\strategy1_sectorcap_trade_log.csv"
DEFAULT_BENCHMARK = r"C:\Projects\trading_engine\data\Historical Daily Data\NIFTY_NS.csv"
DEFAULT_TITLE     = "Strategy 1 — Equity & Drawdown"
OUTPUT_DIR        = r"C:\Projects\trading_engine\logs\charts"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_equity(filepath):
    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def compute_drawdown(equity_series):
    """Returns drawdown series as negative percentages."""
    peak = equity_series.cummax()
    dd   = (equity_series - peak) / peak * 100
    return dd


def analyse_drawdown_periods(dates, equity, dd_series, threshold=-5.0):
    """
    Identify all drawdown periods deeper than threshold%.
    Returns list of dicts with start, trough, recovery, depth, duration_days.
    """
    periods = []
    in_dd   = False
    start   = None
    trough_idx = None

    for i in range(len(dd_series)):
        val = dd_series.iloc[i]

        if not in_dd and val < threshold:
            in_dd      = True
            start      = i
            trough_idx = i

        if in_dd:
            if val < dd_series.iloc[trough_idx]:
                trough_idx = i
            if val >= 0:
                # Recovered
                periods.append({
                    'start'         : dates.iloc[start],
                    'trough'        : dates.iloc[trough_idx],
                    'recovery'      : dates.iloc[i],
                    'depth_pct'     : round(dd_series.iloc[trough_idx], 2),
                    'days_to_trough': (dates.iloc[trough_idx] - dates.iloc[start]).days,
                    'days_to_recover': (dates.iloc[i] - dates.iloc[start]).days,
                    'recovered'     : True
                })
                in_dd = False
                start = None

    # Still in drawdown at end of series
    if in_dd:
        periods.append({
            'start'          : dates.iloc[start],
            'trough'         : dates.iloc[trough_idx],
            'recovery'       : None,
            'depth_pct'      : round(dd_series.iloc[trough_idx], 2),
            'days_to_trough' : (dates.iloc[trough_idx] - dates.iloc[start]).days,
            'days_to_recover': None,
            'recovered'      : False
        })

    return periods


def normalise_to_100(series):
    return series / series.iloc[0] * 100


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main(equity_path, title, trades_path=None, benchmark_path=None):

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # ── Load equity ───────────────────────────────────────────────────
    eq  = load_equity(equity_path)
    dd  = compute_drawdown(eq['portfolio_value'])
    dates = eq['date']

    initial = eq['portfolio_value'].iloc[0]
    final   = eq['portfolio_value'].iloc[-1]
    cagr    = ((final / initial) ** (365 / (dates.iloc[-1] - dates.iloc[0]).days) - 1) * 100
    max_dd  = dd.min()
    sharpe  = (eq['portfolio_value'].pct_change().mean() /
               eq['portfolio_value'].pct_change().std()) * np.sqrt(252)

    # ── Load benchmark ────────────────────────────────────────────────
    bench = None
    if benchmark_path and Path(benchmark_path).exists():
        b = pd.read_csv(benchmark_path)
        close_col = 'Adj_Close' if 'Adj_Close' in b.columns else \
                    'Adj Close' if 'Adj Close' in b.columns else 'Close'
        b['date'] = pd.to_datetime(b['Date'])
        b = b[['date', close_col]].rename(columns={close_col: 'close'})
        b = b[(b['date'] >= dates.iloc[0]) & (b['date'] <= dates.iloc[-1])]
        b = b.sort_values('date').reset_index(drop=True)
        bench = b

    # ── Analyse drawdown periods ──────────────────────────────────────
    dd_periods = analyse_drawdown_periods(dates, eq['portfolio_value'], dd,
                                          threshold=-5.0)

    # ── Print summary ─────────────────────────────────────────────────
    print("=" * 65)
    print(f"  {title}")
    print("=" * 65)
    print(f"  Period        : {dates.iloc[0].date()} to {dates.iloc[-1].date()}")
    print(f"  CAGR          : {cagr:+.2f}%")
    print(f"  Max Drawdown  : {max_dd:.2f}%")
    print(f"  Sharpe Ratio  : {sharpe:.3f}")
    print(f"  Initial       : Rs.{initial:,.0f}")
    print(f"  Final         : Rs.{final:,.0f}")
    print()

    print(f"  DRAWDOWN PERIODS (deeper than -5%)")
    print(f"  {'Start':<12} {'Trough':<12} {'Recovery':<12} "
          f"{'Depth':>7} {'To Trough':>10} {'Recovery':>10}")
    print(f"  {'-'*65}")
    for p in sorted(dd_periods, key=lambda x: x['depth_pct']):
        rec_str  = p['recovery'].strftime('%Y-%m-%d') if p['recovered'] else 'Ongoing'
        rec_days = str(p['days_to_recover']) + 'd' if p['recovered'] else 'N/A'
        print(f"  {str(p['start'].date()):<12} "
              f"{str(p['trough'].date()):<12} "
              f"{rec_str:<12} "
              f"{p['depth_pct']:>6.1f}% "
              f"{str(p['days_to_trough'])+'d':>10} "
              f"{rec_days:>10}")
    print()

    if dd_periods:
        recovered = [p for p in dd_periods if p['recovered']]
        if recovered:
            avg_rec = np.mean([p['days_to_recover'] for p in recovered])
            max_rec = max(p['days_to_recover'] for p in recovered)
            print(f"  Avg recovery time : {avg_rec:.0f} days")
            print(f"  Longest recovery  : {max_rec} days")
    print("=" * 65)

    # ── PLOT ──────────────────────────────────────────────────────────
    fig, axes = plt.subplots(3, 1, figsize=(14, 12),
                              gridspec_kw={'height_ratios': [3, 1.5, 1]})
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.98)

    # Panel 1 — Equity curve
    ax1 = axes[0]
    ax1.plot(dates, eq['portfolio_value'], color='#2196F3', linewidth=1.5,
             label='Strategy')

    if bench is not None:
        bench_norm = normalise_to_100(bench['close']) * (initial / 100)
        ax1.plot(bench['date'], bench_norm, color='#FF9800', linewidth=1.0,
                 alpha=0.7, linestyle='--', label='Nifty 50 (normalised)')

    # Shade drawdown periods
    for p in dd_periods:
        end_dt = p['recovery'] if p['recovered'] else dates.iloc[-1]
        ax1.axvspan(p['start'], end_dt, alpha=0.08, color='red')

    ax1.axhline(y=initial, color='gray', linewidth=0.8, linestyle=':')
    ax1.set_ylabel('Portfolio Value (Rs.)', fontsize=10)
    ax1.legend(fontsize=9)
    ax1.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f'Rs.{x/1000:.0f}K'))
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Equity Curve', fontsize=10, pad=4)

    # Panel 2 — Drawdown
    ax2 = axes[1]
    ax2.fill_between(dates, dd, 0, color='#F44336', alpha=0.4, label='Drawdown')
    ax2.plot(dates, dd, color='#F44336', linewidth=0.8)
    ax2.axhline(y=max_dd, color='darkred', linewidth=0.8, linestyle='--',
                label=f'Max DD {max_dd:.1f}%')
    ax2.set_ylabel('Drawdown (%)', fontsize=10)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_title('Drawdown', fontsize=10, pad=4)

    # Annotate max drawdown
    max_dd_idx = dd.idxmin()
    ax2.annotate(f'{max_dd:.1f}%',
                 xy=(dates.iloc[max_dd_idx], max_dd),
                 xytext=(dates.iloc[max_dd_idx], max_dd - 2),
                 fontsize=8, color='darkred',
                 arrowprops=dict(arrowstyle='->', color='darkred', lw=0.8))

    # Panel 3 — Rolling 6-month returns
    ax3 = axes[2]
    roll_ret = eq['portfolio_value'].pct_change(126) * 100
    colors   = ['#4CAF50' if v >= 0 else '#F44336' for v in roll_ret]
    ax3.bar(dates, roll_ret, color=colors, width=1, alpha=0.7)
    ax3.axhline(y=0, color='black', linewidth=0.8)
    ax3.set_ylabel('6M Return (%)', fontsize=10)
    ax3.grid(True, alpha=0.3)
    ax3.set_title('Rolling 6-Month Returns', fontsize=10, pad=4)

    # Format x-axis on all panels
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, fontsize=8)

    plt.tight_layout()

    # Save
    safe_title = title.replace(' ', '_').replace('—', '-').replace('/', '-')
    out_path   = Path(OUTPUT_DIR) / f"{safe_title}.png"
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"\n  Chart saved: {out_path}")
    plt.show()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--equity',    default=DEFAULT_EQUITY)
    parser.add_argument('--trades',    default=DEFAULT_TRADES)
    parser.add_argument('--benchmark', default=DEFAULT_BENCHMARK)
    parser.add_argument('--title',     default=DEFAULT_TITLE)
    args = parser.parse_args()

    main(
        equity_path    = args.equity,
        title          = args.title,
        trades_path    = args.trades,
        benchmark_path = args.benchmark,
    )