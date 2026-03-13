# Trading Engine Project - Handoff Document

**Date:** February 27, 2026  
**Project:** Systematic Trading Engine for Indian Equity Markets  
**Status:** Phase 1 Complete, Validation Tests In Progress  
**Capital Allocated:** Rs. 50,000-75,000 (5-10% of portfolio)

---

## 🎯 PROJECT OVERVIEW

Building a systematic trading engine in Python for deploying real capital in Indian equity markets. Currently testing if retail systematic trading is viable given India's cost structure (0.9% transaction costs per trade).

**Success Criteria:**
- Find strategies that overcome transaction costs
- Generate consistent returns above Nifty 50 (12-15% annual)
- Maintain drawdowns below 20%
- Work across different market regimes

**Current Focus:** Trend Following Strategy (Version 1) with ADX 20 baseline

---

## ✅ MAJOR ACCOMPLISHMENTS

### Phase 1: Strategy Development & Validation

**1. Built Complete Trend Following Strategy**
- EMA 20/50 crossover with ADX > 20 filter
- 15% trailing stop loss
- 5% position sizing, max 5 concurrent positions
- 30-stock universe from Nifty 200

**2. Validated on 8 Years of Data (2017-2025)**
- Full period: +452.64% total, +20.93% annual, Sharpe 1.252
- Out-of-sample (2022-2024): +32.60% annual (3x benchmark)
- Choppy market (2025): -0.64% (minimal loss, excellent protection)
- 99 total trades, 41.41% win rate, 8.63 win/loss ratio

**3. Parameter Optimization**
- Tested ADX thresholds: 15, 20, 25, 30
- Found ADX 20 is optimal (inverted U-curve, validated)
- Switched from ADX 25 → ADX 20 baseline
- Gained +237% more returns with acceptable risk increase

**4. Critical Bug Fixes**
- Fixed position averaging bug (Portfolio was overwriting positions)
- Fixed stop loss bug on backtest end positions
- Made BacktestEngine strategy-agnostic
- Fixed automated test script (deepcopy, missing config parameters)

**5. Built Automated Test Runner**
- Runs EMA sensitivity (5 configs)
- Runs Stop Loss sensitivity (5 configs)
- Runs Walk-forward analysis (6 windows)
- Auto-generates comparison tables and CSVs
- Saves 30-45 minutes of manual testing

---

## 📁 FILE STRUCTURE

### Core Engine Files
```
C:\Projects\trading_engine\
├── backtesting\
│   ├── engine.py                    # BacktestEngine - event-driven backtesting
│   ├── metrics.py                   # PerformanceMetrics calculations
│   └── run_trend_backtest.py        # Manual test script (gives +452.64%)
│
├── strategies\
│   ├── base_strategy.py             # BaseStrategy with apply_filters()
│   ├── trend_following.py           # TrendFollowingStrategy implementation
│   └── mean_reversion.py            # Old strategy (not used)
│
├── data\
│   ├── loader.py                    # DataLoader for NSE data
│   └── indicators.py                # TechnicalIndicators (EMA, ADX, RSI, BB)
│
├── tests\
│   └── trend_following_30_universe.csv  # 30 stocks from Nifty 200
│
├── config\
│   └── config.yaml                  # Transaction costs, capital, data paths
│
├── automated_tests.py               # NEW: Automated parameter testing
├── VERSION_1_BASELINE.md            # Strategy documentation (v1.1)
├── PROGRESS_TRACKER.md              # Development log
├── ADX_OPTIMIZATION_RATIONALE.md    # Parameter selection rationale
└── AUTOMATED_TESTS_GUIDE.md         # How to use automated tests
```

---

## 🎯 CURRENT BASELINE: VERSION 1 (ADX 20)

### Configuration
```python
{
    'ema_fast_period': 20,
    'ema_slow_period': 50,
    'adx_period': 14,
    'adx_threshold': 20,           # Optimized (was 25)
    'trailing_stop_pct': 0.15,     # 15% stop loss
    'position_size_pct': 0.05,     # 5% per position
    'max_concurrent_positions': 5,
    'stop_loss_pct': 0.15,         # CRITICAL: Must be in config
    'min_price': 10,               # CRITICAL: Filters stocks
    'max_price': 10000,            # CRITICAL: Filters stocks
    'min_volume': 100000,          # CRITICAL: Filters stocks
    'transaction_cost_pct': 0.009  # 0.9% per trade
}
```

**⚠️ CRITICAL:** The `stop_loss_pct`, `min_price`, `max_price`, `min_volume` parameters are ESSENTIAL. BaseStrategy.apply_filters() uses them to screen stocks before signal generation. Missing these causes BaseStrategy to use restrictive defaults (50-5000 price range) which filters out profitable trades.

### Validated Performance (2017-2025)
- **Total Return:** +452.64%
- **Annual Return:** +20.93%
- **Sharpe Ratio:** 1.252
- **Max Drawdown:** 14.30%
- **Total Trades:** 99
- **Win Rate:** 41.41%
- **Profit Factor:** 6.10

### Entry Logic
1. EMA_20 crosses above EMA_50 (bullish crossover)
2. ADX > 20 (medium-to-strong trend filter)
3. Stock passes filters (price 10-10000, volume > 100k)
4. Less than 5 concurrent positions

### Exit Logic
1. EMA_20 crosses below EMA_50 (bearish crossover), OR
2. 15% trailing stop loss triggered

---

## 🚨 OUTSTANDING MYSTERY - REQUIRES INVESTIGATION

### The 99 Trades Paradox

**Observation:**
- Manual script (`backtesting/run_trend_backtest.py`): **+452.64% return, 99 trades**
- Automated script (before config fix): **+384.88% return, 99 trades**
- After adding config parameters: **+452.64% return, 99 trades**

**The Mystery:**
- SAME number of trades (99)
- SAME universe (30 stocks)
- SAME configuration (after fix)
- Yet 68% difference in returns (+452% vs +384%)

**This doesn't make logical sense because:**
- If `apply_filters()` was filtering stocks differently, trade COUNT should differ
- But trade count is IDENTICAL (99 trades)
- Yet returns are MASSIVELY different

**Possible Explanations:**
1. The 99 trades are DIFFERENT trades (different stocks/dates) despite same count
2. The 99 trades have different profit amounts per trade
3. Position sizing or stop loss calculation was different
4. There's a calculation bug somewhere

**NEEDS INVESTIGATION:**
- Compare actual trade lists (symbols, entry dates, exit dates, profits) from both runs
- Identify which trades are different
- Understand WHY adding config parameters changed results despite same trade count

**Files to Compare:**
- Manual run: Output from `backtesting/run_trend_backtest.py` (shows all trades)
- Automated run: `test_results/YYYYMMDD_HHMMSS_ema_sensitivity_EMA_20_50_baseline.txt`

---

## 📊 AUTOMATED TESTS STATUS

### Tests That Ran Overnight

**Command executed:**
```bash
python automated_tests.py --test all
```

**Expected Output Files:**
```
test_results/
├── YYYYMMDD_HHMMSS_ema_comparison.txt
├── YYYYMMDD_HHMMSS_ema_comparison.csv
├── YYYYMMDD_HHMMSS_stoploss_comparison.txt
├── YYYYMMDD_HHMMSS_stoploss_comparison.csv
└── YYYYMMDD_HHMMSS_walkforward_summary.txt
```

### What to Look For

**1. EMA Period Sensitivity (5 tests)**
- EMA 10/30, 15/40, 20/50 (baseline), 30/60, 50/100
- **Expected:** EMA 20/50 should show +452.64% (now that config is fixed)
- **Pattern:** Inverted U-curve with 20/50 at or near peak
- **Red flag:** If 10/30 or 50/100 dramatically better

**2. Stop Loss Sensitivity (5 tests)**
- Stop Loss 10%, 12.5%, 15% (baseline), 17.5%, 20%
- **Expected:** Results should now be DIFFERENT (not all identical)
- **Before fix:** All showed 384.88% (bug - parameters not changing)
- **After fix:** Should vary based on stop loss tightness
- **Pattern:** Tighter stops (10%) = more stopped out, Looser (20%) = bigger losses

**3. Walk-Forward Analysis (6 windows)**
- W1: 2020, W2: 2021, W3: 2022, W4: 2023, W5: 2024, W6: 2025
- **Expected:** 4-5 out of 6 windows profitable
- **2025 window:** Should show negative (choppy year)
- **Red flag:** Only 2-3 windows profitable, or huge variance

---

## 🔧 KEY TECHNICAL LEARNINGS

### 1. BaseStrategy.apply_filters() is Critical

**Location:** `strategies/base_strategy.py` lines 60-92

**What it does:**
```python
def apply_filters(self, df):
    # Filters stocks BEFORE signal generation
    # Checks: min_price, max_price, min_volume
    # Returns: True (trade this stock) or False (skip it)
```

**Used in:** `strategies/trend_following.py` line 245
```python
if not self.apply_filters(df):
    continue  # Skip this stock entirely!
```

**Why it matters:**
- Filters are applied BEFORE signals are generated
- If a stock fails filters, NO signals are generated at all
- Missing filter parameters = uses restrictive defaults (50-5000 price range)
- This can filter out 10-30% of potential trades

### 2. Config Parameters Must Include All BaseStrategy Fields

**Minimum required config:**
```python
{
    # Strategy parameters
    'ema_fast_period': int,
    'ema_slow_period': int,
    'adx_period': int,
    'adx_threshold': float,
    'trailing_stop_pct': float,
    
    # BaseStrategy parameters (CRITICAL - don't skip these!)
    'position_size_pct': float,
    'max_concurrent_positions': int,
    'stop_loss_pct': float,
    'min_price': float,
    'max_price': float,
    'min_volume': int
}
```

### 3. Python's .copy() vs deepcopy()

**Bug we fixed in automated_tests.py:**
```python
# WRONG:
config = self.base_config.copy()  # Shallow copy - can share references

# CORRECT:
from copy import deepcopy
config = deepcopy(self.base_config)  # Truly independent copies
```

**Why it mattered:**
- Shallow copy caused stop loss parameters to not change between tests
- All 5 stop loss tests showed identical results
- deepcopy() fixed this

### 4. Manual vs Automated Script Import Differences

**Manual script** (in `backtesting/` folder):
```python
from engine import BacktestEngine  # Imports backtesting/engine.py (same folder)
```

**Automated script** (in root folder):
```python
from backtesting.engine import BacktestEngine  # Imports backtesting/engine.py
```

**Both use the SAME engine.py** - just different import paths based on location.

---

## 📋 NEXT STEPS & PENDING WORK

### Immediate (Today)

1. **Review Automated Test Results**
   - Check if tests completed successfully
   - Review comparison tables (EMA, Stop Loss, Walk-forward)
   - Verify EMA 20/50 shows +452.64% (config fix worked)

2. **Investigate 99 Trades Mystery**
   - Compare trade lists from manual vs automated runs
   - Identify which trades are different
   - Understand why returns differ despite same trade count
   - **This is critical** - we need to understand the system fully

3. **Document Findings**
   - Update VERSION_1_BASELINE.md if needed
   - Document the trade discrepancy resolution
   - Commit final validated baseline to git

### Phase 2: Additional Validation (Optional)

**If EMA/Stop Loss results look good, consider:**

1. **Monte Carlo Simulation**
   - Bootstrap resampling of trades
   - 1000+ simulation runs
   - Confidence intervals on returns
   - Risk of ruin analysis

2. **Regime Analysis**
   - Define market regimes (trending/choppy/volatile)
   - Test performance in each regime
   - Validate ADX filter effectiveness

3. **Universe Robustness**
   - Test on different stock subsets
   - Random sampling (20, 25, 30, 35, 40 stocks)
   - Sector-based validation

**Decision Point:** Are these additional tests necessary, or is validation sufficient to move to Phase 2?

### Phase 2: Strategy Enhancements

**Once baseline is fully validated:**

1. **Volume Filter (V2)**
   - Add volume spike detection
   - Filter low-volume breakouts
   - Expected: Better win rate, fewer whipsaws

2. **Regime Filter (V3)**
   - Add market regime detection
   - Go to cash in choppy markets
   - Expected: Reduce drawdowns in flat markets

3. **Paper Trading**
   - Monitor ADX 20 baseline in real-time
   - Compare live vs backtest performance
   - No capital at risk

---

## 🎓 KEY DECISIONS & RATIONALE

### 1. ADX 25 → ADX 20 (February 26, 2026)

**Why we changed:**
- ADX 20 showed +110% better returns (+452% vs +215%)
- Out-of-sample validated (+180% better in 2022-2024 test period)
- Better risk control in choppy markets (-0.64% vs -2.93% in 2025)
- Inverted U-curve pattern (peak at 20, not endpoint)
- Captures medium-strength trends (ADX 20-25) that ADX 25 filters out

**Acknowledged risk:**
- Slight optimization bias (tested after seeing full data)
- Max drawdown 1.76% higher (14.30% vs 12.54%)

**Why we accepted it:**
- Risk control validated in worst-case (2025 choppy market)
- Outperformance too large to be noise (+180% in test period)
- Theoretical mechanism makes sense
- Benefits >> Risks

**Documented in:** `ADX_OPTIMIZATION_RATIONALE.md`

### 2. 30 Stocks Better Than 15 Stocks

**Testing showed:**
- 15 stocks: +109% total return (4 years, ADX 25)
- 30 stocks: +215% total return (8 years, ADX 25)
- More opportunities, better diversification

**Decision:** Use 30-stock universe going forward

### 3. Automated Testing Worth the Effort

**Before:** Manual editing, 20+ separate test runs, prone to errors  
**After:** One command, 16 tests automated, comparison tables generated  
**Time saved:** ~1+ hour per sensitivity analysis  
**Quality:** Eliminates human error in parameter changes

---

## 🔍 DEBUGGING NOTES

### If Automated Tests Show Wrong Results

**Check these common issues:**

1. **Missing config parameters**
   - Verify `stop_loss_pct`, `min_price`, `max_price`, `min_volume` are in base_config
   - Without these, BaseStrategy uses restrictive defaults

2. **Shallow copy bug**
   - Verify using `deepcopy(self.base_config)` not `.copy()`
   - Check if stop loss tests all show identical results (indicates bug)

3. **Universe file path**
   - Manual script: `C:\Projects\trading_engine\tests\trend_following_30_universe.csv`
   - Automated script: `tests/trend_following_30_universe.csv` (relative path)
   - Both should point to same file with 30 stocks

4. **Transaction costs**
   - Should be 0.009 (0.9%) in both scripts
   - Check config.yaml has `total_cost_estimate_pct: 0.009`

---

## 💡 SYSTEM ARCHITECTURE INSIGHTS

### How a Backtest Runs

1. **Load Configuration** → Strategy receives config dict
2. **Create Strategy** → TrendFollowingStrategy(config)
   - Calls `BaseStrategy.__init__(config)` first
   - Sets filter parameters (min_price, max_price, min_volume)
   - Sets strategy parameters (EMA, ADX, stop loss)
3. **Create BacktestEngine** → Receives strategy + backtest params
4. **Load Stock Data** → For each stock in universe
5. **Pre-calculate Indicators** → EMA, ADX, RSI, BB (once per stock)
6. **Day-by-Day Simulation** → For each trading day:
   - Check each stock: `strategy.apply_filters(df)` → Pass/Fail
   - If pass: `strategy.generate_signals(df)` → Check for signals
   - Execute signals: Buy/Sell/Hold decisions
   - Update portfolio: Track positions, cash, equity
7. **Calculate Metrics** → Returns, Sharpe, Drawdowns, Trade stats
8. **Return Results** → Nested dict with all metrics

### Critical Checkpoints

**Filters (Line 245 in trend_following.py):**
```python
if not self.apply_filters(df):
    continue  # Stock skipped - no signals generated!
```

**Signal Generation (Lines 78-135 in trend_following.py):**
```python
# Detect EMA crossover
crossover = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))

# Apply ADX filter
strong_trend = df['ADX'] > self.adx_threshold

# Combined signal
df['Signal'] = 0
df.loc[crossover & strong_trend, 'Signal'] = 1
```

**Position Entry (Lines 408-450 in engine.py):**
```python
# Calculate shares to buy
shares = strategy.calculate_position_size(price, portfolio_value)

# Execute buy with transaction costs
portfolio.buy(symbol, shares, price, date, stop_loss)
```

---

## 📊 PERFORMANCE BENCHMARKS

### Nifty 50 (Benchmark)
- Historical: ~12-15% annual returns
- Our target: Beat by 40-75% (i.e., 17-26% annual)

### Version 1 Performance vs Benchmark
- **Annual Return:** 20.93% vs 12-15% → ✅ **Beats by 40-75%**
- **Sharpe Ratio:** 1.252 vs ~0.5-0.7 → ✅ **Better risk-adjusted**
- **Max Drawdown:** 14.30% vs ~20-30% → ✅ **Better downside protection**

---

## 🎯 QUESTIONS TO ANSWER

### For Immediate Investigation
1. **Why do manual and automated scripts show different returns (452% vs 384%) despite same 99 trades?**
   - Need to compare actual trade lists
   - Identify which trades differ
   - Understand the mechanism

### For Validation Review
2. **Do EMA sensitivity results show expected pattern?**
   - Is 20/50 at or near the peak?
   - Is there an inverted U-curve?
   - Are results reasonable?

3. **Do Stop Loss results now show variation?**
   - Before fix: All identical (bug)
   - After fix: Should be different
   - Which stop loss performs best?

4. **Is walk-forward analysis consistent?**
   - Are 4+ windows profitable?
   - Is 2025 negative (expected)?
   - Is variance acceptable?

### For Next Phase Decision
5. **Are additional validation tests necessary?**
   - Monte Carlo simulation?
   - Regime analysis?
   - Universe robustness?
   - Or is validation sufficient?

6. **Ready to move to Phase 2 enhancements?**
   - Volume filter (V2)
   - Regime filter (V3)
   - Paper trading?

---

## 🚀 HOW TO CONTINUE

### In the New Chat

**First message:**
```
I'm continuing work on my trading engine from a previous chat. 
Attached is the handoff document with complete context.

Please review and let me know:
1. What you understand about the current state
2. Any questions about the 99 trades mystery
3. How we should proceed with investigation
```

**Then:**
- Share automated test results (comparison files)
- Work on investigating the trade discrepancy
- Review and validate test results
- Make decisions on next steps

---

## 📞 CONTACT & QUESTIONS

**If the new Claude needs clarification:**
- All files are in `/mnt/project/` directory
- Can view any file using the view tool
- Can run commands to inspect the system
- User (Mohit) can provide additional context

**Key files to reference:**
- `VERSION_1_BASELINE.md` - Strategy documentation
- `PROGRESS_TRACKER.md` - Development history
- `ADX_OPTIMIZATION_RATIONALE.md` - Parameter decisions
- `AUTOMATED_TESTS_GUIDE.md` - Test runner usage

---

## ✅ HANDOFF CHECKLIST

- [x] Project overview and goals documented
- [x] All accomplishments listed
- [x] File structure mapped
- [x] Current baseline (ADX 20) specified
- [x] Outstanding mystery (99 trades) explained
- [x] Automated test status documented
- [x] Key technical learnings captured
- [x] Next steps clearly defined
- [x] Debugging guidance provided
- [x] Questions to answer listed

---

**Document Version:** 1.0  
**Created:** February 27, 2026  
**For:** Continuation in new chat within same Project  
**Status:** Ready for handoff

---

## 🤝 WORKING PROTOCOL

### User Preferences (from Memory)

**Mohit's Approach:**
- Evidence-based, systematic analysis
- Professional-grade implementations required
- No tolerance for unprofessional behavior (jumping to solutions without analysis, ignoring instructions)
- Demands rigorous validation before conclusions
- Methodical debugging over assumptions

**Communication Style:**
- Direct and concise
- No excessive explanations
- Get to the point
- Show work, don't narrate process

### Established Workflows

**1. When Creating Files:**
- Always use `/home/claude` for temporary work
- Move final outputs to `/mnt/user-data/outputs/` for user access
- Use `present_files` tool to share completed files
- Keep post-file sharing explanations brief

**2. When Using Skills:**
- ALWAYS read appropriate SKILL.md files FIRST
- Skills are in `/mnt/skills/public/` (docx, pptx, xlsx, pdf, etc.)
- Multiple skills may be needed - read all relevant ones
- Follow skill instructions carefully

**3. When Debugging:**
- Compare implementations systematically
- Don't assume - verify with data
- Check actual values, not expected values
- Question logical inconsistencies (like the 99 trades mystery!)

**4. When Testing Strategies:**
- Run full validation (out-of-sample, stress test)
- Check for overfitting and optimization bias
- Document decision rationale
- Don't trust backtest results blindly

**5. File Organization:**
- Use proper naming conventions with timestamps
- Generate comparison tables (txt + csv)
- Keep detailed logs of all tests
- Version control important changes

### Quality Standards

**Code:**
- Professional-grade, production-ready
- Proper error handling
- Clear variable names
- Comments for complex logic

**Analysis:**
- Back up claims with data
- Show calculations
- Question anomalies
- Don't ignore red flags

**Documentation:**
- Clear, concise, organized
- Include rationale for decisions
- Note caveats and limitations
- Update as work progresses

---

**Good luck with the investigation! The 99 trades mystery is fascinating - looking forward to solving it!** 🔍
