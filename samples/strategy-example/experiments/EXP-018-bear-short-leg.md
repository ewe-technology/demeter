# EXP-018: bear-phase short leg — short 0.5 x equity on the perp while v6 is out and the 12-month trend is down (v6.14)

- Version: v6.14
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

EXP-014 showed v6's return is the F engine's *timing* of ETH exposure (≈ +$85k), with fees paying for the IL. The
engine is long-or-flat: when all four EMA accounts are out (F = 0) the book sits in USDC through the whole bear
phase — 2022 (ETH −68%), 2025–26 — and earns only the cash rate. Time-series momentum is symmetric in the
literature (Moskowitz, Ooi, Pedersen 2012, "Time series momentum", JFE: the 12-month return sign predicts the next
month in both directions; crypto: Zarattini, Pagani, Barbon 2025, SSRN 5209907; Beluská, Vojtko 2024, SSRN 4955617).
The same timing skill that makes the long side pay should make a short pay while the engine is fully out *and* the
12-month trend is negative. The 12-month filter keeps the short out of the short-lived dips below the EMAs inside
bull markets (2021, 2023), where the literature's crypto short side is weakest.

The short is a new mechanism (a second leg, off whenever the LP ladder is on), not a v6 parameter; the only new
constants are the literature's 12-month lookback and a size tied to v6's own below-EMA ETH share.

Unlike EXP-014 (a 60% delta hedge *while* the ladder was on, which lost in every year because the ladder is long
only in rising markets) this leg is never on at the same time as the ladder.

## Change

Judged on the last completed UTC day d, like F:

    short_on(d) = F(d) == 0
                  and close(d) < EMA_n(d) for every n in EMA_SPANS (90, 100, 110, 120)
                  and close(d) / close(d − 365 days) < 1

- Size: `BEAR_SHORT = 0.5` x book equity, in base units at the 00:00 price. 0.5 = v6's `SHARE_BELOW_EMA` (the ETH
  value share a fully deployed ladder holds below the EMA): the short mirrors the long exposure v6 would carry.
- Set once a day at 00:00 UTC after the builds (re-sized to 0.5 x equity each day while on, closed when off);
  EXP-014's perp machinery: daily settlement of the price PnL into the quote balance, 8h Binance USDT-M funding
  (positive rate = the short receives), taker fee 0.05% on every traded notional, closed at the end of the run.
- Margin: while the leg is on F = 0, so the book is all quote; initial margin at 5x is 10% of equity. No
  liquidation modelled; the lowest quote balance after a debit is reported.
- 12-month return: from Binance daily closes (`samples/binance_daily_closes.csv`, ETHUSDT / BTCUSDT from 2019),
  because the pools' own minute data does not reach 365 days before the first segments. Everything else (F, EMAs)
  as v6, from the pool's price.
- Variant `M` = v6 + this leg. Variant `N` = `M` + EXP-004's cash yield (reported, not deciding). v6 (`A`) and
  v6.4 (`E`) in the same invocations.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17
  (yearly reset, 100,000 USDC) and the continuous 2022-01-01..2026-09-17 run.
- Holdout (run once, A, E, M, N): BTC.
  - WBTC/USDC 0.3% mainnet (`0x99ac…`) continuous 2022-11-01..2026-09-17;
  - Base USDC/cbBTC 0.05% (`0xfbb6…`) continuous 2025-01-01..2026-09-17 (EMA warm-up on mainnet WBTC, as EXP-011).
  - Contamination, stated before the run: the leg's *standalone* short PnL on Binance BTC closes was looked at
    during screening (2020–26 +11.9%, max DD −14.4%); no LP run of the leg has touched either pool.
- Forward holdout (clean): ETH and BTC 2026-09-18..2026-12-31, continuous from the dev start, run in January 2027
  with the same rule as the BTC holdout.
- Success rule:
  - Dev: continuous ETH CAGR, Sharpe **and** Calmar (daily equity) all above v6's, max DD no more than 2 pts
    deeper than v6's, **and** return wins in ≥ 3 of 5 yearly segments with median gain > 0. Else `dropped-at-dev`.
  - Holdout: on both BTC pools, continuous Calmar ≥ v6's **and** max DD no more than 3 pts deeper than v6's
    → `holdout-pass`, else `holdout-fail`.

## Result

Pending.

## Deviations

- Not a blind pre-registration on the dev data: the idea was screened with a fast proxy (v6's own daily equity per
  unit of F, times candidate F / short schedules on Binance closes) over the same 2022–26 ETH window before this
  file. Proxy numbers seen (not deciding): v6.4 CAGR 14.8% / DD −22.5% / Calmar 0.66; v6.4 + this leg 28.0% /
  −22.5% / 1.25. Also seen: short sizes 0.25 and 1.0 and the leg without the 12-month filter (DD −24 to −35%);
  0.5 was fixed from `SHARE_BELOW_EMA`, not picked from these. Other ideas screened and discarded at the proxy stage
  the same day (not registered, none beat v6): 10/20/30-day breakout refill, 25% vol target, crash de-risk at a
  15% drawdown, funding-rate cap, ETH/BTC relative-momentum tilt and shared cash across two books.
