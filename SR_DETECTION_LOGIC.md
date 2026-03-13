# S/R Detection Module — Complete Logic Summary
**Strategy 2: S/R Retest Pullback**
*Version 1.1 | March 2026 — ATR-based proximity thresholds added*

---

## STEP 1 — FRACTAL DETECTION

Identify swing highs and lows on the daily chart using Williams' fractal definition:
- Swing high at day i: high[i] > high of previous 2 AND next 2 bars
- Swing low at day i: low[i] < low of previous 2 AND next 2 bars
- Lookback window: 60–120 trading days

Research basis: Williams (1995), Carter Mastering the Trade (2005), Brooks Trading Price Action (2011)

---

## STEP 2 — ZONE CLUSTERING

Cluster nearby swing prices into zones using 1% tolerance.
Price levels are zones, not precise points.

Research basis: Murphy Technical Analysis of Financial Markets (1999), Bulkowski Encyclopedia of Chart Patterns (2005)

---

## STEP 3 — SIGNIFICANCE FILTER

For each zone apply three binary gates — ALL three must be met:

| Criterion | Threshold | Research Basis |
|---|---|---|
| Touch count | ≥ 2 touches | Bulkowski (2005) daily chart |
| Age | ≥ 5 trading days since first touch | Bulkowski (2005), Carter (2005) |
| Volume | ≥ 1 touch at volume ≥ 1.4× 20-day average | O'Neil institutional participation threshold |

Keep ALL qualifying zones. Count is an output of criteria, not a fixed input.

---

## STEP 4 — TREND DIRECTION

Determine near-term trend using 20-day price change:
- Down > 2%: seek support zones below current price
- Up > 2%: seek resistance zones above current price
- Neutral (within ±2%): nearest zone in either direction

---

## STEP 5 — PROXIMITY CLASSIFICATION

Proximity thresholds use **ATR(14) × 0.5** rather than fixed percentages.

ATR adapts to each stock's actual volatility — thresholds automatically tighten for low-volatility stocks and widen for high-volatility ones. For NSE stocks ATR(14) × 0.5 typically produces 0.8–1.2%.

Research basis: Wilder (1978) ATR design principle. Connors and Alvarez Short-Term Trading Strategies That Work (2008) — ATR-based proximity thresholds outperform fixed percentages across cross-sectional volatility differences.

For each qualifying zone in the travel direction:

| Classification | Threshold |
|---|---|
| Testing | Price within 1× ATR(14) × 0.5 of zone boundary |
| Approaching | Price within 1× to 3× ATR(14) × 0.5 of zone boundary |
| Inactive | Price beyond 3× ATR(14) × 0.5 from zone boundary |
| Flip Risk flag | Strong opposing zone within 2× ATR(14) × 0.5 of primary zone |

**Fixed percentage fallback (configurable):** 1% testing, 1–3% approaching, 3% inactive.
Used only if ATR cannot be computed due to insufficient data.

---

## STEP 6 — SIGNAL PRIORITY

| Signal | Condition |
|---|---|
| BUY | Downtrend + Testing Primary Support |
| ALERT | Downtrend + Approaching Primary Support |
| MONITOR | Testing Secondary Support |

---

## CONFIGURABLE PARAMETERS

All thresholds configurable for backtest validation. No parameter is hardcoded.

| Parameter | Default | Backtest Range |
|---|---|---|
| Fractal lookback N (bars each side) | 2 | 2, 3 |
| Zone clustering tolerance | 1% | 0.5%, 1%, 1.5% |
| Minimum touch count | 2 | 2, 3 |
| Minimum age | 5 trading days | 3, 5, 7, 10 |
| Volume multiplier | 1.4× | 1.2×, 1.4×, 1.6× |
| Volume reference period | 20-day | 20-day, 50-day |
| Lookback window | 60–120 trading days | 60, 90, 120 |
| Proximity method | ATR(14) × 0.5 | ATR or fixed % |
| ATR multiplier | 0.5 | 0.3, 0.5, 0.75 |
| Fixed % fallback — testing | 1% | configurable |
| Fixed % fallback — approaching | 3% | configurable |
| Trend threshold | 2% over 20 days | 1%, 2%, 3% |

---

*All thresholds calibrated for 15–45 day holding period on daily chart. Starting parameters subject to backtest validation.*

---

## APPENDIX — Plain Language Explanation

### How the S/R Detection Module Works — A Simple Walkthrough

Imagine you are watching **BHARATFORG.NS**. It was in our top 10% momentum universe 2 weeks ago but dropped out last week. It is now a Scenario B candidate — a stock that had genuine momentum and is now consolidating.

---

**STEP 1 — Find the Pivot Points**

Look at the last 60-120 days of daily price data. Find every point where price made a local peak or trough — specifically where a day's high is higher than the 2 days before and 2 days after it (swing high), or a day's low is lower than the 2 days before and 2 days after it (swing low). These are the natural turning points in price.

Think of it as marking every bump and dip on a price chart.

---

**STEP 2 — Group Nearby Levels Into Zones**

Multiple swing points often cluster near the same price. Instead of treating 1,248 and 1,255 as two separate levels, group them into one zone if they are within 1% of each other. Price reacts to zones, not precise numbers.

---

**STEP 3 — Filter Out Weak Zones**

Not every zone is worth trading. Keep only zones that pass all three tests:

- Price visited the zone at least **2 times** — it has been tested and held
- Price spent at least **5 trading days** around the zone — real consolidation happened there, not just a quick touch
- At least one visit happened on **unusually high volume** — 40% above the 20-day average — which means institutions were actively trading at that level

If a zone fails even one test, discard it. Only strong, institutionally validated zones survive.

---

**STEP 4 — Determine Which Direction Price Is Moving**

Calculate how much the stock has moved over the last 20 days:

- Down more than 2% — stock is pulling back, look for **support zones below** current price
- Up more than 2% — stock is pushing up, look for **resistance zones above** current price
- Flat within 2% — neutral, look at the nearest zone in either direction

For BHARATFORG pulling back after a momentum move, this will correctly identify — look for support below.

---

**STEP 5 — How Close Is Price to the Zone**

Rather than using a fixed distance like 1%, we use **ATR** — a measure of how much this specific stock moves on an average day. Multiply ATR by 0.5 to get approximately half an average day's move. This adapts to each stock's actual volatility automatically.

Using this dynamic distance:

- **Testing** — price is right at the zone boundary, within half an ATR. The retest is happening now.
- **Approaching** — price is between half an ATR and 1.5 ATR away. Getting close, watch it.
- **Inactive** — price is more than 1.5 ATR away. Nothing happening yet.
- **Flip Risk** — there is a strong opposing zone within 2 ATR on the other side. The trade has no room to breathe. Flag it as risky.

---

**STEP 6 — Generate the Signal**

Combine everything into an actionable output:

- **BUY signal** — stock is in a pullback AND price is currently testing a strong support zone
- **ALERT** — stock is in a pullback AND price is approaching a strong support zone
- **MONITOR** — price is testing a secondary support zone further down

---

**The full picture in one sentence:**

Find price levels where institutions have repeatedly traded, confirm they are significant using objective criteria, determine whether the current pullback is heading toward one of those levels, and flag it when price is close enough to act on.

