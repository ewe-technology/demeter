# EXP-001: spot trend sleeve (v6.1) — half of the deployed capital held as spot ETH instead of LP

- Version: v6.1
- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 78cc9af · Result commit: see registry

## Hypothesis

v6's F is a strong timing signal but the LP throws its directional value away. On ETH 2022-01..2026-09
(daily closes, no costs) holding F x ETH as spot returns +426% (max DD −45%, Sharpe 0.96) and 0.5 x F x ETH
+163% (max DD −25%, Sharpe 0.96), against v6's +85% (max DD −23%, Sharpe 0.73) where "principal is flat, the
return is fee income" (`V6_VALIDATION.md` §4). The ±20% valley is short gamma: in the trends F selects it sells
ETH on the way up (v6 loses −9.2% a year in "up, low vol" and trails the plain LP in 2023/2024, §2 and §5).

Holding part of the deployed capital as spot ETH, sized by the same F, keeps the trend exposure the signal
earns while the rest keeps earning fees. The reserve (1 − F) is unchanged, so the down-market defence stays.

## Change

One structural switch, `SPOT_SLEEVE = 0.5` (v6: 0):

- Every (re)build (first LP, range exit, F follow) targets, of equity E: (1 − F) x E idle quote (as v6),
  0.5 x F x E spot base held outside the bands, 0.5 x F x E in the ±20% inverted-gaussian ladder with v6's
  s rule (70% / 50% ETH by close vs EMA100) inside the ladder.
- The spot sleeve drifts with price between rebuilds; it is reset at every rebuild.
- F follow: "deployed" = (LP value + free base value) / E, same thresholds (1/8, full/empty tolerance).
- Everything else identical to v6: engine (EMA 90–120, stops, refill), width, shape, range-exit rule, fees
  paid out in quote and not reinvested, costs (pool fee + price impact on every swap, the sleeve's included).
- 0.5 is fixed a priori (half and half), not tuned; no other value is run.

## Pre-registration

- Development data (in-sample, all seen): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025,
  2026-01-01..09-17 (yearly reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3%
  2022-11-01..2026-09-17 reported.
- Holdout (run once, baseline + this variant only): WBTC/WETH 0.05% mainnet
  (`0x4585fe77225b41b697c938b018e2ac67ac5a20c0`), never run by any v6 test. ETH is the base (risk asset), WBTC
  the quote (numeraire and reserve), 2 WBTC start. Yearly segments 2023, 2024, 2025, 2026-01-01..09-17,
  plus the continuous 2022-11-01..2026-09-17 run (reported).
- Success rule:
  - Dev: wins (net return > v6) in ≥ 3 of 5 ETH segments, median gain > 0 pts, and continuous ETH max DD no
    more than 5 pts worse than v6. Otherwise `dropped-at-dev`, no holdout.
  - Holdout: wins in ≥ 3 of 4 segments and median gain > 0 pts → `holdout-pass`, else `holdout-fail`.

## Result

Development, ETH/USDC 0.05%, yearly reset, 100,000 USDC (net return; max DD from the demeter metric):

| test | v6 | this | gain | max DD v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +12.0% | +4.4 | 21.5% → 26.8% |
| 2023 | +32.2% | +42.9% | +10.7 | 13.9% → 18.2% |
| 2024 | +36.4% | +35.9% | −0.5 | 26.7% → 36.6% |
| 2025 | +16.3% | +37.5% | +21.2 | 26.9% → 31.2% |
| 2026-01..09-17 | +18.7% | +27.2% | +8.5 | 12.0% → 16.6% |

Wins 4/5, median gain +8.54 pts.

Continuous runs (daily equity):

| run | total | CAGR | max DD | Sharpe | vol | longest underwater |
|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | 21.1% | 491 d |
| ETH this | +198.0% | 26.1% | **−33.6%** | 0.86 | 33.1% | 455 d |
| WBTC/USDC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 17.3% | 400 d |
| WBTC/USDC this | +131.7% | 24.2% | −23.7% | 0.98 | 25.3% | 400 d |

The sleeve halves the fee income (ETH 2025: $12.8k vs $20.8k) and more than makes up for it with the trend,
but it rides every pullback until the EMA exit / 20% stop moves F, so each year's drawdown deepens 4–10 pts.

Verdict: **dropped at dev** — wins 4/5 and median +8.5 pts pass, but continuous ETH max DD −33.6% is 10.8 pts
worse than v6 (rule: ≤ 5). The holdout was not run and stays unused. Calmar improved (0.61 → 0.78), so the
return per unit of drawdown is better; the sleeve simply carries more risk than the rule allows.

## Deviations

- Before this pre-registration the F-weighted spot statistics above were computed from daily closes of ETH/USDC
  (in-sample) and also of the holdout pool's WBTC/WETH closes, in the other orientation (BTC priced in ETH:
  F x BTC +67% vs hold +147%). No strategy run touched the holdout pool.
- Smoke tests before the pre-registration commit, outside every pre-registered window: ETH 2021-12-20..26
  (F 0) and 2021-11-01..07 (F 1: LP value and fees halve, first swap 85k = sleeve 50k + 70% of the 50k ladder).
  The holdout pool was only loaded (2021-11-02..03 prices), not backtested.
