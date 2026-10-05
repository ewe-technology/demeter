# EXP-052: idle reserve LP'd in the Uniswap USDC/USDT pool (v6.39)

- Jira: QUAN-933
- Status: holdout-pass
- Pre-registration commit: 990a6ad · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino).

## Hypothesis

v6 keeps (1 − F) x equity as idle USDC (mean F 0.585 in 2025, `V6_VALIDATION.md`; 124 days of the year at F = 0). That
cash earns nothing. EXP-004 put the same reserve in Aave and passed dev 5/5 and holdout 3/3 with a shallower drawdown,
but lending is out of scope since 2026-10-01. The pure-LP version: LP the reserve in the mainnet Uniswap v3 USDC/USDT
pool, ±0.1% around the peg. Its fee income is uncorrelated with ETH/BTC and its price risk is the peg only, so CAGR
should rise by (stable fee APR x mean reserve share) with the drawdown unchanged or shallower: CAGR and Calmar both up
on both assets. Literature pass 2026-10-05 (pool-average USDC/USDT 0.01% APY 1.4-4.6% a year, DefiLlama; Gauntlet ALM review 1-4%).

## Change

`STABLE_LP = "pool"` (variant `AO`, `v6_validate.py`): once a day at 00:00 UTC the reserve (quote held outside the
ladder minus the paid-out fees and income) earns the previous day's net return of $1 in the USDC/USDT position, booked
as income like the fees (paid out, never deployed). Daily return from `samples/make_stable_lp_series.py` →
`samples/stable_lp_daily.csv`:

- position: one range [−10, +10) ticks (±0.1%) around tick 0, never moved; reference size $100k (its own liquidity in
  the denominator of its fee share);
- fees: per minute with the close tick in range, pool fee x swap volume x L / (L_pool + L); out of range nothing;
- mark to market in USDC at each day's last close tick (a depeg moves the position into the cheaper coin);
- pool: USDC/USDT 0.05% `0x7858e59e...` before 2021-11-15 (the 0.01% pool did not exist), USDC/USDT 0.01% `0x3416cf6c...`
  from 2021-11-15 (S3 to 2025-11-30, RPC download for the rest and for 2021-05..11);
- switching: every change of the reserve between two daily accruals pays 0.01% on half the moved amount (the half
  that is USDT has to be swapped); gas reported nowhere (as for the ladder: not charged).

Constants fixed here, not searched: ±10 ticks, $100k reference, 0.01% switch fee. Everything else identical to v6.

## Pre-registration

Pre-registered together with EXP-053 and EXP-054 and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev
  windows (different time, different price path), warm-up from Binance daily closes (`BINANCE_WARM=1`):
  - H5 ETH/USDC 0.05% mainnet 2021-05-06..2021-12-31 (the pool's first day to the day before the ETH dev window);
  - H4 WBTC/USDC 0.3% mainnet 2022-01-01..2022-10-31 (the BTC bear before the WBTC dev window).
  Freshness: v6's own numbers on both windows are known (EXP-040..051); this variant never ran there. The cross-pool
  windows H1-H3 share the dev price paths and are not run.
- Success rule (improvement level only; daily equity net of price impact, Calmar = CAGR / |max DD|;
  `experiments/judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly
    wins ≥ 3 of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and
    max DD no more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, `A,AO,AP,AQ`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +7.9% | +0.3 |
| 2023 | +32.2% | +32.9% | +0.7 |
| 2024 | +36.4% | +37.6% | +1.2 |
| 2025 | +16.3% | +17.7% | +1.5 |
| 2026-01..09-17 | +18.7% | +19.1% | +0.4 |

Wins 5/5, median +0.71 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | stable LP income | rebuilds | mean F |
|---|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | — | 147 | 0.650 |
| ETH this | +89.1% | 14.5% | -22.2% | 0.75 | 0.65 | $86.5k | $3.70k | 147 | 0.650 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | — | 106 | 0.672 |
| WBTC this | +89.0% | 17.9% | -17.1% | 1.04 | 1.04 | $61.7k | $3.48k | 106 | 0.672 |

(The "LP fees" column of the run CSV includes the stable income for this variant: $90.2k / $65.1k; the ladder's own fees
are v6's, since the ladder is identical.)

Holdout, time-split out-of-time (`BINANCE_WARM=1`, `A,AO`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | stable LP income |
|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | — |
| H5 ETH 2021-05-06..12-31 this | +5.6% | 8.7% | -29.8% | 0.41 | 0.29 | $1.08k |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | — |
| H4 WBTC 2022-01-01..10-31 this | +2.6% | 3.2% | -12.4% | 0.25 | 0.26 | $0.26k |

Verdict: **holdout-pass** (improvement level) — dev: ETH CAGR 14.5% vs 14.0%, Calmar 0.65 vs 0.61, max DD −22.2% vs −22.8%;
WBTC CAGR 17.9% vs 17.3%, Calmar 1.04 vs 0.97, max DD −17.1% vs −17.8%; ETH yearly wins 5/5. Time-split holdout: H5 ETH 2021
CAGR 8.7% vs 7.0%, Calmar 0.29 vs 0.23; H4 WBTC 2022 CAGR 3.2% vs 2.9%, Calmar 0.26 vs 0.23; max DD shallower on both.
Reading: the gain is the idle reserve's yield (+0.3 to +1.5 pts a year, larger in years with more cash and higher stable
volume: 2024 6.4% stable fee APR), not a better ETH/BTC ladder — rebuilds, F and the ladder's fees are v6's to the dollar,
so the equity curve is v6's plus a small, almost riskless income stream. It is a deployable improvement of v6's cash
handling; it is not evidence of a better trading rule. The H4 margin (+0.25 pts in ten months) is small; the sign follows
mechanically from a positive stable yield, so the out-of-time pass confirms the mechanism, not a forecastable edge.

## Deviations

- The stable LP's yearly fee yield was printed while building `stable_lp_daily.csv` (an input check, before this file
  was committed): 2021 (May-Dec) 3.8%, 2022 1.3%, 2023 2.2%, 2024 6.4%, 2025 2.9%, 2026 (to 09-17) 0.9%; mark to
  market < 0.1% a year. The range width (±10 ticks) was fixed before that print.
- A 3.5-week smoke test (ETH 2023-06-01..06-25, variants `A,AO,AP,AQ`) checked that the code runs; its numbers are not
  used.
- This is a near-copy of v6 (same ladder, same F): it is not independent evidence about the ETH/BTC strategy, only about
  the reserve.
