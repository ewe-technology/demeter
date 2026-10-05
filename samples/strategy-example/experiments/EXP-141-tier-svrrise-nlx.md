# EXP-141: fee tier: EXP-124's WBTC half + rise rebuild, EXP-130's ETH half (v6.127)

- Jira: QUAN-1026
- Status: holdout-pass
- Pre-registration commit: 50be075 · Result commit: d65083e
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

With routing, the rise rebuild no longer hurt the 0.3% pool (EXP-137: WBTC 18.9% vs 18.5%); added here to EXP-124's WBTC half.

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool`, `REBUILD_ON_RISE`; below 0.3%: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`. Variant `EC`.

## Pre-registration

Pre-registered together with EXP-139..143 (same commit), run with `A` (v6) in `A,EA,EB,EC,ED,EE` per window.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..081) and both windows have been used for other variants; this
  variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `AEAEBECEDEE`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +13.7% | +6.1 |
| 2023 | +32.2% | +38.9% | +6.7 |
| 2024 | +36.4% | +34.9% | -1.4 |
| 2025 | +16.3% | +17.3% | +1.0 |
| 2026-01..09-17 | +18.7% | +19.1% | +0.4 |

Wins 4/5, median +1.04 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +108.6% | 16.9% | -24.7% | 0.85 | 0.68 | $94.5k | $0.34k | 136 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +110.2% | 21.1% | -13.8% | 1.23 | 1.53 | $64.5k | $-5.05k | 100 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +16.0% | 25.4% | -25.4% | 0.80 | 1.00 | $25.3k | $3.33k | 31 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +7.5% | 9.1% | -11.1% | 0.50 | 0.82 | $14.0k | $-0.55k | 17 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev: ETH CAGR 16.9% (= EXP-130), WBTC 21.1% vs 17.3% (EXP-124 21.0%), Calmar 1.53. Holdout: H5 ETH = EXP-130 (+16.0%); H4 WBTC 2022 +7.5% vs +2.4%, but below EXP-124 without the rise rule (+9.6%): on the 0.3% pool the rise rebuild costs 2.1 pts out of time even with routing. Passes against v6, worse than EXP-130 on WBTC.

## Deviations

- Designed after EXP-134..138's results. EXP-130's ETH half (v6.75 + cross-asset refill) is the only ETH half besides v6.75 with its own out-of-time gain (H5 +16.0% vs v6.75 +13.5%); these pairs add one more ETH-side rule to it (rise rebuild, macro restore, two-day range-exit confirmation), each new on H5, or the rise rebuild on the WBTC half (new on H4). EXP-142 is EXP-126 (one rule) plus the rise rebuild. The rise rebuild added little out of time in EXP-134 / 137 (+0.1 / +0.3 pt); these runs say whether it adds on top of the cross-asset rule.
