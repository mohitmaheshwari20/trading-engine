"""
Aggregate Exit Reason Analysis
Parses trade breakdown by exit reason and provides aggregated summary.

Usage:
1. Paste your exit reason data into 'exit_reasons.txt'
2. Run: python analyze_exits.py
"""

import re

def parse_exit_line(line):
    """
    Parse a single exit reason line.
    
    Example formats:
    - SELL: EMA bearish crossover - Fast=1040.57 crossed below Slow=1040.88 Count:   1  Win Rate:   0.0%  Avg P/L: -13.61%
    - Stop Loss                 Count:   5  Win Rate:   0.0%  Avg P/L: -17.62%
    """
    # Extract count
    count_match = re.search(r'Count:\s+(\d+)', line)
    if not count_match:
        return None
    
    count = int(count_match.group(1))
    
    # Extract win rate
    wr_match = re.search(r'Win Rate:\s+([\d.]+)%', line)
    win_rate = float(wr_match.group(1)) if wr_match else 0.0
    
    # Extract avg P/L
    pl_match = re.search(r'Avg P/L:\s+([+-]?[\d.]+)%', line)
    avg_pl = float(pl_match.group(1)) if pl_match else 0.0
    
    # Categorize exit type
    if 'Stop Loss' in line:
        category = 'Stop Loss'
    elif 'EMA bearish crossover' in line or 'SELL:' in line:
        category = 'Bearish Crossover (EMA)'
    elif 'Backtest End' in line:
        category = 'Backtest End'
    else:
        category = 'Other'
    
    return {
        'category': category,
        'count': count,
        'win_rate': win_rate,
        'avg_pl': avg_pl
    }


def aggregate_exits(filename):
    """
    Read file and aggregate exit reasons by category.
    """
    categories = {}
    
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or 'Count:' not in line:
                continue
            
            parsed = parse_exit_line(line)
            if not parsed:
                continue
            
            cat = parsed['category']
            
            if cat not in categories:
                categories[cat] = {
                    'total_count': 0,
                    'total_wins': 0,
                    'weighted_pl_sum': 0  # count * avg_pl for weighted average
                }
            
            # Accumulate
            categories[cat]['total_count'] += parsed['count']
            categories[cat]['total_wins'] += int(parsed['count'] * parsed['win_rate'] / 100)
            categories[cat]['weighted_pl_sum'] += parsed['count'] * parsed['avg_pl']
    
    return categories


def print_summary(categories):
    """
    Print aggregated summary.
    """
    print("="*80)
    print("AGGREGATED EXIT REASON ANALYSIS")
    print("="*80)
    print()
    
    # Sort by count (descending)
    sorted_cats = sorted(categories.items(), key=lambda x: x[1]['total_count'], reverse=True)
    
    total_trades = sum(cat['total_count'] for cat in categories.values())
    total_wins = sum(cat['total_wins'] for cat in categories.values())
    
    print(f"{'Exit Reason':<30} {'Count':>8} {'% of Total':>12} {'Win Rate':>12} {'Avg P/L':>12}")
    print("-"*80)
    
    for cat_name, stats in sorted_cats:
        count = stats['total_count']
        pct_of_total = (count / total_trades * 100) if total_trades > 0 else 0
        win_rate = (stats['total_wins'] / count * 100) if count > 0 else 0
        avg_pl = stats['weighted_pl_sum'] / count if count > 0 else 0
        
        print(f"{cat_name:<30} {count:8d} {pct_of_total:11.1f}% {win_rate:11.1f}% {avg_pl:+11.2f}%")
    
    print("-"*80)
    overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"{'TOTAL':<30} {total_trades:8d} {'100.0%':>12} {overall_win_rate:11.1f}%")
    print("="*80)
    
    # Key insights
    print("\nKEY INSIGHTS:")
    print("-"*80)
    
    for cat_name, stats in sorted_cats:
        count = stats['total_count']
        win_rate = (stats['total_wins'] / count * 100) if count > 0 else 0
        avg_pl = stats['weighted_pl_sum'] / count if count > 0 else 0
        
        if cat_name == 'Bearish Crossover (EMA)':
            print(f"✓ {count} trades exited on bearish crossover ({win_rate:.1f}% win rate, {avg_pl:+.2f}% avg)")
        elif cat_name == 'Stop Loss':
            print(f"✓ {count} trades hit stop loss ({avg_pl:.2f}% avg loss)")
        elif cat_name == 'Backtest End':
            print(f"✓ {count} trades still open at backtest end ({avg_pl:+.2f}% avg)")
    
    print()


if __name__ == "__main__":
    try:
        categories = aggregate_exits('exit_reasons.txt')
        print_summary(categories)
        
    except FileNotFoundError:
        print("ERROR: exit_reasons.txt not found!")
        print()
        print("Please create a file named 'exit_reasons.txt' and paste your exit reason data.")
        print()
        print("Example format:")
        print("SELL: EMA bearish crossover - Fast=280.94 crossed below Slow=281.04 Count:   1  Win Rate: 100.0%  Avg P/L: +144.59%")
        print("Stop Loss                 Count:   5  Win Rate:   0.0%  Avg P/L: -17.62%")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
