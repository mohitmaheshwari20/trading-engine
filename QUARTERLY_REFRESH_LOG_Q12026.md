# Quarterly Refresh Log
**Purpose:** Audit trail of every quarterly screening refresh
**Started:** March 2026

---

## Q1 2026 Refresh - 03 March 2026

### Inputs
- Chartink results: 396 stocks
- Nifty 200 universe: 201 symbols
- Intersection before ADX filter: 47 stocks
- After ADX >= 20 filter: 44 stocks
- Manual removals: 0
- Final deployed universe: 44 stocks

### Output File
screened_universe_20260303.csv

### Nifty 200 Changes vs Previous Quarter
First refresh - no previous quarter to compare against.
Baseline established with 201 symbols.

### Universe Changes vs Previous Quarter
First refresh - no previous quarter to compare against.
Baseline of 44 stocks established.

### ADX Filter Note
3 stocks passed Chartink ADX > 20 but failed our computed ADX >= 20:
- BANKBARODA.NS (ADX: 19.49)
- AXISBANK.NS (ADX: 18.6)
- BAJAJ-AUTO.NS (ADX: 18.04)

Decision: Use our computed ADX as source of truth. Chartink is first-pass only.
Script updated to apply ADX >= 20 post-intersection filter.

### Overlap with Curated 30
14 of the original curated 30 stocks appeared independently in the screen:
CGPOWER, APLAPOLLO, TITAN, BAJFINANCE, POLYCAB, LT, SBIN, NTPC, ONGC,
TATASTEEL, SUNPHARMA, DRREDDY, EICHERMOT, APOLLOHOSP

16 curated stocks absent - all confirmed in Nifty 200 but not currently trending:
SUZLON, ATGL, WAAREEENER, ADANIGREEN, ADANIENT, BSE, DIXON, KPITTECH,
KALYANKJIL, SWIGGY, MAZDOCK, RVNL, COCHINSHIP, IRFC, TRENT, PAYTM

Interpretation: Screen correctly excludes stocks no longer in active uptrend.
This is expected and correct behaviour.

### Market Context
- Chartink raw output: 396 stocks - neutral to mild bull market conditions
- Markets closed on 03 March 2026 (data as of 02 March 2026)

### Sector Distribution
To be reviewed against screened_universe_20260303.csv before paper trading begins.
Sector concentration rule: no single sector > 40% of universe.

### Manual Removals
None this quarter.

### Open Positions Review
No live positions at this stage - paper trading begins Q1 2026 (March).
This refresh establishes the starting universe for paper trading.

### Paper Trading Note
Paper trading setup begins 04 March 2026.
This is the first forward-looking test of the screened universe.
Results to be reviewed at Q2 June 2026 refresh.

---

## Q2 2026 Refresh - [First week of July 2026]

To be completed at next quarterly refresh.

---
