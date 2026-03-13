# Quarterly Refresh Workflow
**Version:** 1.0
**Last Updated:** March 2026
**Frequency:** Once per quarter (March / June / September / December)
**Estimated time:** 45-60 minutes

---

## Overview

Every quarter you run this workflow to update the stock universe the trading engine
operates on. It replaces the previous quarter's universe with a fresh set of stocks
that are currently trending and pass all screening criteria.

This is a fully manual process for now. Automation is a future phase.

---

## When to Run

Run this workflow at the start of each quarter, before deploying any new positions:

| Quarter | Run in | NSE Rebalancing |
|---------|--------|-----------------|
| Q1 | First week of January | December rebalancing |
| Q2 | First week of April | March rebalancing |
| Q3 | First week of July | June rebalancing |
| Q4 | First week of October | September rebalancing |

**Important:** Run on a trading day when markets are open and Chartink data is live.
Do not run on a market holiday — Chartink results will reflect stale prices.

---

## Pre-Requisites

Before starting, ensure the following are ready:

- [ ] Python environment is working
- [ ] Price data files are updated to the latest trading date
- [ ] Chartink account is accessible (free tier)
- [ ] Screener.in account is accessible (free tier, for manual sanity check)
- [ ] Previous quarter's `screened_universe_YYYYMMDD.csv` is saved and accessible
- [ ] Trading engine is not mid-execution (complete any open signals first)

---

## Step 1 — Update Nifty 200 List (10 minutes)

NSE updates the Nifty 200 constituent list after each rebalancing. Update your local
file to reflect the current composition.

**Actions:**
1. Go to: https://www.nseindia.com/products-services/indices-nifty200-index
2. Download the latest constituent CSV
3. Extract the Symbol column (symbols will be in format like `RELIANCE`)
4. Append `.NS` to each symbol (e.g. `RELIANCE` → `RELIANCE.NS`)
5. Save as `nifty200_symbols.txt` at `C:\Projects\Backtesting System\nifty200_symbols.txt`
   — overwrite the previous file

**Verification:**
- Open `nifty200_symbols.txt` and confirm it has approximately 200 symbols
- Confirm format is one symbol per line e.g. `RELIANCE.NS`

**Note any changes:**
- Which symbols were added this quarter?
- Which symbols were removed?
- Do you currently hold any positions in removed symbols? (flag for Step 5)

**For any newly added symbols — download price data:**
1. Identify symbols that are new to the list this quarter
2. Download historical price data for each new symbol using your data download process
3. Save to `C:\Projects\Backtesting System\data\SYMBOL_NS.csv` using the standard filename format
4. Verify the file has sufficient history (at least 28 rows — ideally 1 year or more for reliable ADX)
5. Do not proceed to Step 3 until all new symbol data files are in place — the intersection script will flag missing files as warnings and exclude those stocks from the output

---

## Step 2 — Run Chartink Technical Screen (10 minutes)

**Actions:**
1. Log into Chartink (https://chartink.com)
2. Open your saved scan — conditions are:
   - Daily ADX(14) > 20
   - Daily EMA(20) > Daily EMA(50)
   - Daily Close > Daily EMA(200)
   - Universe: NSE cash segment
3. Run the scan
4. Export results as CSV
5. Save as `Stock Screener.csv` at `C:\Projects\trading_engine\screening\Stock Screener.csv`
   — overwrite the previous file

**Verification:**
- Output should have several hundred stocks (typically 200-400 depending on market conditions)
- If output is below 100 stocks, the market is likely in a choppy or bear phase — note this
- If output is above 500 stocks, the market is in a strong bull phase — note this

---

## Step 3 — Run the Intersection Script (5 minutes)

**Actions:**
1. Open terminal / command prompt
2. Navigate to screening folder:
   ```
   cd C:\Projects\trading_engine\screening
   ```
3. Run the script:
   ```
   python screening_intersection.py
   ```
4. Note the console output — specifically:
   - Intersection count
   - Missing data file count (should be 0 if data is updated)
   - Final ranked universe count
   - Any warnings

5. The output file `screened_universe_YYYYMMDD.csv` is saved automatically

**Verification:**
- Final ranked universe should be between 20 and 80 stocks
- If below 20: DO NOT proceed to deployment — see Fallback Rules section
- If above 80: Market is in a strong trend phase, proceed normally
- Missing data files should be 0 — if not, update price data for those symbols first

---

## Step 4 — Manual Sanity Check (15 minutes)

Review the new universe before deploying. Two checks:

### 4a — Fundamental Spot Check
For the top 10-15 stocks by ADX rank, open each on Screener.in free tier
(https://www.screener.in) and flag any stock showing:

- Interest coverage < 1.5 (cannot service debt from operations)
- Negative operating cash flow for 2+ consecutive years
- Revenue declining for 2+ consecutive years
- Promoter pledge > 20%

**Action if flagged:** Remove the flagged stock from the universe manually.
Document which stock was removed and why in the Refresh Log (Step 7).

### 4b — Sector Concentration Check
Open `screened_universe_YYYYMMDD.csv` and group stocks by sector.

**Rule:** No single sector should represent more than 40% of the final universe.

| Universe Size | Max stocks from one sector |
|---------------|---------------------------|
| 44 stocks | 17 stocks |
| 35 stocks | 14 stocks |
| 25 stocks | 10 stocks |
| 20 stocks | 8 stocks |

**Action if breached:** Remove the lowest-ranked stocks (by ADX) in the over-represented
sector until the 40% rule is satisfied. Document removals in the Refresh Log.

---

## Step 5 — Compare New Universe to Previous Quarter (10 minutes)

This is the most important step. Compare the new screened universe to last quarter's
universe and identify:

### Stocks that EXITED the universe (were in previous quarter, not in new)

These stocks are no longer trending by our screen.

**Rule — Stocks with open positions:**
- If you currently hold a position in an exited stock AND it has not yet hit stop loss
  AND EMA20 is still above EMA50: **Hold until the next EMA crossover exit signal**
  — do not force-exit just because it left the screen
- If the stock has already crossed below EMA20/EMA50: **Exit at next opportunity**
- Do not take any new entries in exited stocks this quarter

**Rule — Stocks without open positions:**
- Simply do not trade them this quarter. No action needed.

### Stocks that ENTERED the universe (new this quarter, not in previous)

These are new trending opportunities identified by the screen.

**Rule:**
- These are eligible for new entries this quarter
- Entry is triggered by the trading engine signal (EMA crossover + ADX > 20)
  — do not pre-emptively buy just because they entered the universe
- Apply normal position sizing rules

### Stocks that REMAIN in universe (in both previous and new)

No action needed. Continue holding open positions and taking new signals normally.

---

## Step 6 — Update Trading Engine Universe File (5 minutes)

Once Steps 4 and 5 are complete and you have a final clean universe:

**Actions:**
1. If you made any manual removals in Step 4, edit `screened_universe_YYYYMMDD.csv`
   to remove flagged stocks
2. Extract the Symbol column from the final universe CSV
3. Save as the trading engine universe input file
   (format and location depends on how your engine reads the universe — update accordingly)
4. Verify the engine is reading the new universe correctly before the quarter begins

---

## Step 7 — Update Refresh Log (5 minutes)

Maintain a running log of each quarterly refresh. This is your audit trail and helps
identify patterns over time.

**Add an entry to `QUARTERLY_REFRESH_LOG.md` with:**

```
## Q[X] [Year] Refresh — [Date]

### Inputs
- Chartink results: [X] stocks
- Nifty 200 universe: [X] symbols
- Intersection: [X] stocks
- Final universe after manual review: [X] stocks

### Nifty 200 Changes
- Added: [symbols]
- Removed: [symbols]

### Universe Changes vs Previous Quarter
- Exited universe: [symbols]
- Entered universe: [symbols]
- Unchanged: [X] stocks

### Manual Removals (Step 4)
- [Symbol]: [reason]

### Sector Distribution
- [Sector]: [X] stocks ([X]%)

### Market Context
- Chartink raw output: [X] stocks (indicates [bull/neutral/choppy] market)
- Any notable observations

### Open Positions Review
- Stocks in portfolio that exited universe: [symbols + action taken]
```

---

## Fallback Rules

### If final universe < 20 stocks
Do not deploy new capital this quarter. The market is likely choppy or in a downtrend.
- Hold existing open positions with normal stop loss rules
- Re-run the screen mid-quarter (6 weeks in) to check if conditions have improved
- Do not lower ADX threshold to force more stocks — this defeats the purpose of the filter

### If Chartink raw output < 100 stocks
This signals a broad market downturn. Even if intersection produces 20+ stocks, proceed
with caution:
- Reduce position size from 5% to 3% per position this quarter
- Tighten mental stop loss awareness (do not override stop loss rules, but be alert)

### If a data file is missing for an intersection stock
Update the price data for that symbol before running the script again.
Do not deploy with missing data files.

---

## Checklist Summary

Print and use this checklist each quarter:

```
QUARTERLY REFRESH CHECKLIST — Q[X] [Year]

[ ] Step 1: Nifty 200 list updated from NSE website
[ ] Step 1: nifty200_symbols.txt saved and verified (~200 symbols)
[ ] Step 1: Nifty 200 changes noted (additions/removals)
[ ] Step 1: Price data downloaded for any newly added symbols

[ ] Step 2: Chartink scan run on a live trading day
[ ] Step 2: Stock Screener.csv saved to screening folder
[ ] Step 2: Raw output count noted

[ ] Step 3: screening_intersection.py run successfully
[ ] Step 3: No missing data files
[ ] Step 3: Final universe >= 20 stocks

[ ] Step 4a: Top 10-15 stocks checked on Screener.in
[ ] Step 4a: Distressed stocks flagged and removed
[ ] Step 4b: Sector concentration checked
[ ] Step 4b: 40% rule satisfied

[ ] Step 5: New universe compared to previous quarter
[ ] Step 5: Exited stocks reviewed — open position rules applied
[ ] Step 5: Entered stocks noted — eligible for new entries

[ ] Step 6: Trading engine universe file updated
[ ] Step 6: Engine reading new universe correctly

[ ] Step 7: Quarterly refresh log updated

READY TO DEPLOY: [ ] YES  [ ] NO (reason: _______________)
```

---

## Files Reference

| File | Location | Updated |
|------|----------|---------|
| nifty200_symbols.txt | C:\Projects\Backtesting System\ | Every quarter |
| Stock Screener.csv | C:\Projects\trading_engine\screening\ | Every quarter |
| screened_universe_YYYYMMDD.csv | C:\Projects\trading_engine\screening\ | Every quarter |
| screening_intersection.py | C:\Projects\trading_engine\screening\ | Only if script changes |
| QUARTERLY_REFRESH_LOG.md | C:\Projects\trading_engine\screening\ | Every quarter |

---

## Automation Roadmap (Future)

Steps that can be automated in later phases:

| Step | Automation Option |
|------|------------------|
| Step 1: Nifty 200 update | Python script to scrape NSE website |
| Step 2: Chartink screen | Python script using yfinance to replicate screen |
| Step 3: Intersection script | Already automated |
| Step 4b: Sector check | Add to intersection script |
| Step 6: Universe file update | Add to intersection script |
| Step 7: Refresh log | Add to intersection script |

Steps 4a (fundamental sanity check) will remain manual indefinitely unless a
free fundamental data source is identified.
