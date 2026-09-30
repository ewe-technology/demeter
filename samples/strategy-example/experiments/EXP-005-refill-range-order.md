# EXP-005: refills as quote-only range orders instead of market buys (v6.5)

- Version: v6.5
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

EXP-003 located where v6's principal goes: its worst episode (2024-03 → 09, v6 −20%) is a chain of F round trips.
Below the EMAs the engine refills on +5..15% bounces, and every refill makes v6 rebuild the whole ladder and
market-buy base at the top of the bounce; the next leg down exits at market again. F went 1 → 0 → 1 four times in
five months. The refill signal itself is valuable (gating it on the EMA destroys F's timing value, EXP-003), so the
signal stays; what changes is the execution.

An LP can buy on a dip without predicting it: a quote-only range order below the price converts into base only if
the price comes down into it, and earns fees while it does. Placing each F increment that way buys the bounce's
pullback instead of its top, and adds nothing when the rally runs away (then the range-exit rebuild deploys as v6).
Exits stay market sells, so the defence is unchanged.

## Change

`REFILL_ORDER = True` (v6: False):

- When the daily F follow check finds F above the deployed fraction by ≥ 1/8 (or the full-deployment tolerance),
  the increment (target − current) x equity (quote) goes into one new position over the ladder's quote side: from
  two tick spacings off the current price to the ladder's lower edge (−20% in price). No swap, no rebuild; the
  existing ladder stays as it is.
- F falling by ≥ 1/8, and every range exit, rebuild exactly as v6 (market swap to the s share, orders included).
- Range exits are judged on the span of the last built ladder, not on the orders (which sit off the price by
  design). With no ladder (F was 0) the span is the ladder v6 would have built at the order's price.
- No new constant: the order spans v6's own lower half. Everything else identical to v6.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A) and this (F) in the same invocation.
- Holdout (run once, v6 + this only): WBTC/WETH 0.05% mainnet (`0x4585fe77…`), ETH base, WBTC quote, 2 WBTC,
  yearly segments 2023, 2024, 2025, 2026-01-01..09-17 plus the continuous 2022-11-01..2026-09-17 (reported).
  EXP-001..003 were dropped at dev and EXP-004 does not use it, so no strategy run has touched this pool.
- Success rule (as EXP-001..003, against v6):
  - Dev: wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, and continuous ETH max DD (daily equity) ≥ −27.8%.
    Otherwise `dropped-at-dev`.
  - Holdout: wins in ≥ 3 of 4 segments and median gain > 0 pts → `holdout-pass`, else `holdout-fail`.

## Result

| test | v6 | this | gain |
|---|---|---|---|

Verdict:

## Deviations

- Designed after EXP-001..003's dev results and drawdown analysis (all dev data in-sample).
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
- Smoke test before the pre-registration commit, outside every pre-registered window: ETH 2021-05-10..06-30
  (crash, engine barely warmed up): 8 refill orders, rebuilds 11 → 6, fees $3.0k → $6.7k, price impact
  $0.9k → $4.7k (the filled orders are sold in one larger market swap at the next exit; the impact model is
  quadratic in size), net −31.0% (v6) → −27.3%.
