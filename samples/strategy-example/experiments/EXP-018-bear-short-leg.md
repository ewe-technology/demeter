# EXP-018: bear-phase short leg — short 0.5 x equity on the perp while v6 is out and the 12-month trend is down (v6.14)

- Version: v6.14
- Jira: [QUAN-865](https://ewetechnology.atlassian.net/browse/QUAN-865)
- Status: holdout-fail
- Pre-registration commit: 759afa7 · Result commit: ______

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

Development, ETH/USDC 0.05% mainnet, yearly reset, 100,000 USDC (A, E, M, N in one invocation per segment):

| test | v6 | this (M) | gain | max DD v6 → this | short days |
|---|---|---|---|---|---|
| 2022 | +7.6% | +47.0% | +39.4 | 21.5% → 14.9% | 62 |
| 2023 | +32.2% | +33.6% | +1.4 | 13.9% → 12.6% | 12 |
| 2024 | +36.4% | +36.4% | 0.0 (tie: never on) | 26.7% → 26.7% | 0 |
| 2025 | +16.3% | +22.7% | +6.5 | 26.9% → 26.9% | 56 |
| 2026-01..09-17 | +18.7% | +37.5% | +18.8 | 12.0% → 15.0% | 28 |

Wins 4/5 plus one exact tie (2024, the leg never fired; the script counts it as a win by 3e-11), median +6.47 pts.

Continuous ETH 2022-01-01..2026-09-17 (daily equity):

| run | total | CAGR | max DD | Sharpe | Calmar | LP fees | short PnL / funding / fees | short days |
|---|---|---|---|---|---|---|---|---|
| v6 (A) | +85.4% | 14.0% | −22.8% | 0.73 | 0.61 | $86.5k | | |
| v6.4 (E) | +101.0% | 16.0% | −20.7% | 0.82 | 0.77 | $86.5k + $15.6k interest | | |
| **this (M)** | **+219.3%** | **28.0%** | −23.4% | **1.05** | **1.20** | $122.3k | +$92.6k / −$0.5k / −$2.0k | 158 |
| M + cash yield (N) | +245.7% | 30.1% | −21.3% | 1.12 | 1.41 | $122.8k + $21.9k interest | +$96.4k / −$0.5k / −$2.1k | 158 |

Dev rule: CAGR, Sharpe and Calmar all above v6, max DD 0.6 pts deeper (limit 2), wins ≥ 3/5 with median > 0 →
**dev passes**. The short leg adds +$92.6k of price PnL on 158 of 1,721 days, and the extra equity compounds into
larger ladders later (LP fees $86k → $122k).

Holdout (run once), continuous, A, E, M, N in one invocation per pool:

| pool | run | total | CAGR | max DD | Sharpe | Calmar | short PnL | short days |
|---|---|---|---|---|---|---|---|---|
| Base USDC/cbBTC 0.05%, 2025-01..2026-09-17 | v6 | +22.3% | 12.5% | −15.7% | 0.93 | 0.79 | | |
| | this (M) | +30.2% | 16.7% | −13.8% | 1.02 | **1.21** | +$7.3k | 36 |
| | N | +34.0% | 18.7% | −12.3% | 1.13 | 1.51 | +$7.5k | 36 |
| WBTC/USDC 0.3% mainnet, 2022-11..2026-09-17 | v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.97 | | |
| | this (M) | +80.8% | 16.5% | −18.1% | 0.91 | **0.91** | +$1.9k | 46 |
| | N | +91.7% | 18.3% | −17.6% | 1.00 | 1.04 | +$2.4k | 46 |

WBTC calendar years v6 → this: 2022-11..12 −8.5% → −11.7%, 2023 +32.0% → +25.0%, 2024 +27.1% → +27.3%,
2025 +10.8% → +10.7%, 2026 +9.1% → +16.2%.

Verdict: **holdout-fail** — Base cbBTC passes (Calmar 1.21 vs 0.79, DD 1.9 pts shallower) but mainnet WBTC fails
Calmar (0.91 vs 0.97; DD 0.3 pts deeper, inside the floor). The pre-registered rule needs both pools. The loss is
the bear-to-bull turn: the short is still on at the end of 2022 and into the January 2023 squeeze (BTC +40% in
weeks while the 12-month return is still negative), costing ≈ 10 pts that the 2026 bear leg only partly earns back.
On ETH, whose 2022–26 path had deeper and longer bear phases, the leg more than doubles v6's total and doubles its
Calmar; on BTC, with one sharp V-shaped bottom, it is roughly a wash. Candidate status: best full-history ETH result
so far, not robust across assets; the clean forward holdout (2026-09-18..12-31) still runs in January 2027.

## Deviations

- Not a blind pre-registration on the dev data: the idea was screened with a fast proxy (v6's own daily equity per
  unit of F, times candidate F / short schedules on Binance closes) over the same 2022–26 ETH window before this
  file. Proxy numbers seen (not deciding): v6.4 CAGR 14.8% / DD −22.5% / Calmar 0.66; v6.4 + this leg 28.0% /
  −22.5% / 1.25. Also seen: short sizes 0.25 and 1.0 and the leg without the 12-month filter (DD −24 to −35%);
  0.5 was fixed from `SHARE_BELOW_EMA`, not picked from these. Other ideas screened and discarded at the proxy stage
  the same day (not registered, none beat v6): 10/20/30-day breakout refill, 25% vol target, crash de-risk at a
  15% drawdown, funding-rate cap, ETH/BTC relative-momentum tilt and shared cash across two books.
- A two-month smoke test (ETH 2022-05-01..06-30, A and M) ran after the pre-registration commit to check the code
  (M +21.9% vs v6 −7.9%, 40 short days); it is inside the dev window and was deleted, not used.
- Dev and holdout ran on 4 workers per invocation, the WBTC and Base holdouts concurrently (staggered start). No
  reruns. The dev "wins" column counts the 2024 tie as a win (3e-11); reported here as 4/5 + 1 tie.
