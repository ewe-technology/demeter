# EXP-002: spot sleeve with a trailing stop (v6.2)

- Version: v6.2
- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 7e0d91f · Result commit: 5e84d3b

## Hypothesis

EXP-001 (v6.1) showed the spot sleeve earns the trend (continuous ETH +198% vs +85%, dev wins 4/5, median
+8.5 pts) but was dropped for drawdown: −33.6% vs −22.8%. Its three worst episodes are v6's own three
(2024-03→09, 2022-04→07, 2025-08→12, each ETH −40..−70% from the top) made deeper: the sleeve rides the fall until
the 90–120 day EMA exits move F. A per-sleeve trailing stop at v6's own lower-stop level cuts the sleeve after a
20% fall from its high, well before the EMA exits, while the LP half and the reserve behave exactly as in v6.1.

## Change

v6.1 (`SPOT_SLEEVE = 0.5`) plus `SLEEVE_STOP = 0.80` (v6.1: none). No new free constant: 0.80 is v6's `LOWER_STOP`.

- `sleeve_high` = highest completed daily close since the sleeve was last bought.
- Daily (with the F follow check, judged on the last completed daily close): if the close < 0.80 x `sleeve_high`,
  sell the free base (the sleeve) for quote. The sleeve is then "stopped": rebuilds place (1 − 0.5) x F x E in
  the ladder as usual and keep the sleeve's share in quote, and the F follow compares the book with (1 − 0.5) x F.
- Re-arm (next rebuild buys the sleeve again, pushed by the F follow when the gap is ≥ 1/8) when either
  (a) F rises above the lowest F seen since the stop (an engine refill), or (b) a daily close exceeds `sleeve_high`.
- Everything else identical to v6.1 / v6: engine, ladder, width, s rule, costs.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A), v6.1 (B, reference only) and this (C) in the same invocation.
- Holdout (run once, v6 + this only): WBTC/WETH 0.05% mainnet (`0x4585fe77…`), ETH base, WBTC quote, 2 WBTC,
  yearly segments 2023, 2024, 2025, 2026-01-01..09-17 plus the continuous 2022-11-01..2026-09-17 (reported).
  EXP-001 was dropped at dev, so this pool is still untouched by any strategy run.
- Success rule (same as EXP-001, against v6):
  - Dev: wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, and continuous ETH max DD (daily equity) no more
    than 5 pts worse than v6 (i.e. ≥ −27.8%). Otherwise `dropped-at-dev`.
  - Holdout: wins in ≥ 3 of 4 segments and median gain > 0 pts → `holdout-pass`, else `holdout-fail`.

## Result

Development, ETH/USDC 0.05%, yearly reset (v6.1 = EXP-001 for reference):

| test | v6 | v6.1 | this | gain vs v6 | max DD v6 → this | sleeve stops |
|---|---|---|---|---|---|---|
| 2022 | +7.6% | +12.0% | +2.2% | −5.4 | 21.5% → 28.3% | 1 |
| 2023 | +32.2% | +42.9% | +42.9% | +10.7 | 13.9% → 18.2% | 0 |
| 2024 | +36.4% | +35.9% | +38.9% | +2.5 | 26.7% → 35.2% | 1 |
| 2025 | +16.3% | +37.5% | +37.5% | +21.2 | 26.9% → 31.2% | 0 |
| 2026-01..09-17 | +18.7% | +27.2% | +29.6% | +10.9 | 12.0% → 15.1% | 1 |

Wins 4/5, median gain +10.67 pts.

Continuous runs (daily equity):

| run | total | CAGR | max DD | Sharpe | stops |
|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | |
| ETH v6.1 | +198.0% | 26.1% | −33.6% | 0.86 | |
| ETH this | +182.1% | 24.6% | **−32.4%** | 0.85 | 3 |
| WBTC/USDC v6 | +85.6% | 17.3% | −17.8% | 1.01 | |
| WBTC/USDC this | +131.7% | 24.2% | −23.7% | 0.98 | 0 (identical to v6.1) |

Why the stop barely fired: a 20% fall also exits the ±20% ladder, and that rebuild re-buys the sleeve and resets
its high at the fallen price, so the stop level keeps moving down with the price.

Verdict: **dropped at dev** — wins 4/5 and median +10.7 pts pass, but continuous ETH max DD −32.4% is 9.6 pts
worse than v6 (rule: ≤ 5). Holdout not run. Follow-up: EXP-003 keeps the high across rebuilds.

## Deviations

- Designed after seeing EXP-001's dev results and drawdown episodes (the whole dev set is in-sample by design).
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
- Smoke test before the pre-registration commit, outside every pre-registered window: ETH 2021-05-10..06-30
  (May 2021 crash, engine barely warmed up): one sleeve stop fired; v6 -31.0%, v6.1 -35.9%, this -30.2%.
