# EXP-074: no range-exit rebuild (ablation) (v6.61)

- Jira: QUAN-957
- Status: dropped-at-dev
- Pre-registration commit: 5bb711c · Result commit: 79ce351
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6 rebuilds the real ladder when the daily price is outside its ±20% span (19 of 147 ETH rebuilds, 7 of 106 WBTC). This goal's results say the exit rebuild is where the assets disagree most (EXP-057: rebuilding without the swap helped WBTC and hurt ETH; EXP-056: earlier exits hurt both). The ablation asks what the exit rebuild is worth at all: without it a ladder the price has left waits, out of range and one-sided, until the engine's next F change rebuilds it (the follow rule). Expected: lower return in trends (the ladder idles), less swap cost and fewer rebuys at the extremes.

## Change

`NO_EXIT_REBUILD = "all"` (variant `BM`): the range-exit check never triggers a rebuild; follow rebuilds (|F − deployed| ≥ 12.5%) and builds from an empty book are v6's. No constant.

## Pre-registration

Pre-registered together with the other two ablations of the same commit (EXP-073..075) and run in the same invocations as
`A` (v6). EXP-074 and EXP-075 are near-copies of each other.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..063); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `ABLBMBN`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +4.1% | -3.6 |
| 2023 | +32.2% | +32.1% | -0.1 |
| 2024 | +36.4% | +23.7% | -12.7 |
| 2025 | +16.3% | +5.3% | -11.0 |
| 2026-01..09-17 | +18.7% | +15.8% | -2.9 |

Wins 0/5, median -3.56 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +66.3% | 11.4% | -17.0% | 0.72 | 0.67 | $60.5k | $0.23k | 133 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +84.8% | 17.2% | -14.5% | 1.30 | 1.18 | $41.3k | $0.62k | 100 |

Verdict: **dropped-at-dev** — ETH CAGR 11.4% vs 14.0% (Calmar 0.67 vs 0.61, max DD −17.0%), wins 0/5; WBTC CAGR 17.2% vs 17.3% with Calmar 1.18 vs 0.97 (max DD −14.5%). Holdout not run. Reading: without the range-exit rebuild the ladder idles out of range until the next F change (320 skipped daily checks on ETH): drawdowns fall on both assets because an out-of-range ladder is out of the market, and ETH loses fee income (.5k vs .5k) in trends. The exit rebuild is worth about 2.6 pts of ETH CAGR and costs drawdown; on WBTC it is roughly neutral in return.

## Deviations

- Ablations chosen after EXP-052..072 (this goal's results: every rebuild-rule change moved ETH and WBTC in opposite directions; the engine ablations showed which rules carry v6's edge). Smoke test ETH 2022-05-01..06-30 (`BL,BM,BN`, inside the dev data; v6's total there, −7.9%, was seen in EXP-055's smoke test): share 70% −10.5%, the two exit ablations −7.9% with one skipped exit each. The ablations have no constant to adjust.
- The WBTC continuous segment crashed on the shared `~/.demeter` cache before any backtest ran and was rerun alone (CLAUDE.md gotcha).
