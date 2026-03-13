# Position Sizing Module — One-Page Spec
**Strategy 2: S/R Retest Pullback**
*Version 1.0 | March 2026*

---

## Hypothesis

The size of each position must be determined by the risk of the trade, not by convenience or instinct. A fixed fractional approach — risking a fixed percentage of total capital on every trade — ensures that no single losing trade can meaningfully damage the portfolio, while still deploying capital efficiently. This is the most widely validated position sizing method in systematic trading literature.

Research basis: Van Tharp, Trade Your Way to Financial Freedom (1997) — fixed fractional sizing as the baseline for systematic strategies. O'Neil, How to Make Money in Stocks — 1-2% risk per trade for new strategies. Schwager, Market Wizards — consistent position sizing cited as a common trait across professional traders.

---

## What the Position Sizing Module Does

The module sits downstream of the entry signal module. It receives a confirmed entry signal with a specific entry price and stop loss, and computes exactly how many shares to buy so that if the stop loss is hit, the loss equals no more than 2% of total capital.

---

## Core Formula

```
Risk Amount (₹)  = Total Capital × Risk Per Trade %
                 = ₹1,00,000 × 2%
                 = ₹2,000

Stop Distance (₹) = Entry Price - Stop Loss Price

Raw Shares        = Risk Amount / Stop Distance
                  = ₹2,000 / Stop Distance

Position Value (₹) = Raw Shares × Entry Price
```

Raw shares are rounded down to the nearest whole number — never rounded up, as rounding up increases risk beyond the 2% limit.

---

## Capital Availability Check

After computing raw shares, the module checks whether sufficient capital is available to fund the position.

```
Required Capital = Raw Shares × Entry Price

If Required Capital <= Available Capital:
    Final Shares = Raw Shares  (full position)

If Required Capital > Available Capital:
    Final Shares = floor(Available Capital / Entry Price)  (scaled down)
    Actual Risk  = Final Shares × Stop Distance  (will be less than ₹2,000)
```

**Scale down, never skip.** A smaller position is better than no position when the signal is valid. Research basis: Van Tharp (1997) — partial positions preserve participation in valid setups while respecting capital constraints.

If scaled down shares = 0 (entry price exceeds available capital entirely), the trade is skipped and flagged as INSUFFICIENT CAPITAL.

---

## Portfolio Heat Limit

Maximum total risk across all open positions at any time: **6% of total capital = ₹6,000**.

With 2% risk per trade, this allows up to 3 concurrent positions before hitting the heat limit. A fourth signal is only actioned if the total risk across existing open positions is below 6%.

**Why 6% and not a fixed position count:**
A hard position count ignores the actual risk of each trade. Two wide-stop trades can carry more risk than three tight-stop trades. Portfolio heat measures what you actually stand to lose if all stops are hit simultaneously — a more accurate and professional constraint.

Research basis: Van Tharp, Trade Your Way to Financial Freedom (1997) — portfolio heat as the correct measure of total portfolio risk. 6-8% maximum heat recommended for swing trading strategies.

**Formula:**


**In practice with ₹1,00,000:**
Capital availability will typically be the binding constraint before heat is reached. At typical position sizes of ₹30,000–₹50,000, capital runs out at 2-3 positions. The heat limit is the professional backstop for edge cases where stops are unusually tight and many small positions could otherwise accumulate.

If portfolio heat limit is reached, new signals are flagged as MAX HEAT REACHED and not actioned until a position closes and heat drops below 6%.

---

## Available Capital Calculation

```
Available Capital = Total Capital - Capital In Open Strategy 2 Positions

Capital In Open Position = Entry Price × Shares Held
```

Available capital is recomputed before every new signal using **Strategy 2 positions only**. Strategy 1 positions are excluded — they run on a separate capital allocation and must not interfere with Strategy 2 sizing.

**Implementation:** open_positions.csv includes a Strategy column. The position sizing module filters for Strategy=2 rows only before computing deployed capital and portfolio heat.

---

## Output Per Signal

| Field | Description |
|---|---|
| symbol | NSE symbol |
| entry_price | Confirmed entry price from entry signal module |
| stop_loss | Stop loss price from entry signal module |
| stop_distance | Entry price - stop loss price |
| stop_distance_pct | Stop distance as % of entry price |
| risk_amount | Actual ₹ at risk (≤ ₹2,000) |
| raw_shares | Shares computed from risk formula before capital check |
| final_shares | Shares after capital availability check |
| position_value | Final shares × entry price |
| capital_used_pct | Position value as % of total capital |
| portfolio_heat_pct | Total risk % across all open positions before this trade |
| new_heat_pct | Total portfolio heat % after adding this trade |
| sizing_note | FULL / SCALED DOWN / INSUFFICIENT CAPITAL / MAX HEAT REACHED |

---

## Configurable Parameters

| Parameter | Default | Notes |
|---|---|---|
| Total capital | ₹1,00,000 | Update when capital changes |
| Risk per trade | 2% | Configurable for backtesting |
| Max portfolio heat | 6% | Total risk across all open positions |
| Round shares | Floor | Never round up |

---

## Exit Position Sizing

**At Target 1 (partial exit):**
```
Shares to sell = floor(Final Shares × 0.50)  (50% of position)
Shares to hold = Final Shares - Shares to sell
```

**At Target 2 or stop loss:**
```
Shares to sell = All remaining shares
```

Partial exit percentage (default 50%) is inherited from the entry signal module configuration and applied consistently.

---

## Worked Example

**Signal:** BSE.NS, Entry = ₹2,600, Stop Loss = ₹2,470

```
Stop Distance    = 2,600 - 2,470 = ₹130
Risk Amount      = ₹1,00,000 × 2% = ₹2,000
Raw Shares       = 2,000 / 130 = 15.38 → 15 shares (floor)
Position Value   = 15 × 2,600 = ₹39,000
Capital Used     = 39%

Available Capital after this trade = ₹1,00,000 - ₹39,000 = ₹61,000

Second position (hypothetical): Entry = ₹500, Stop = ₹470
Stop Distance    = ₹30
Raw Shares       = 2,000 / 30 = 66 shares
Position Value   = 66 × 500 = ₹33,000
Capital Check    = ₹33,000 < ₹61,000 — FULL position

Available Capital after both trades = ₹61,000 - ₹33,000 = ₹28,000
Portfolio heat   = (1950/100000 + 1980/100000) x 100 = 3.93% — below 6% limit
Third signal     = allowed if capital available and heat < 6%
```

---

*All parameters configurable. Capital figure updated manually when deploying additional capital or withdrawing profits. Module reads open positions from open_positions.csv maintained by the daily workflow.*
