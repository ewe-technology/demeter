# EXP-073: ETH share 70% in both trend states (ablation of the EMA100 share switch) (v6.60)

- Jira: QUAN-956
- Status: holdout-fail
- Pre-registration commit: 5bb711c · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6 builds its ladder with 70% of the value in ETH while the close is above EMA100 and 50% below. EXP-046 removed the upper state (50% always): shallower drawdowns on every window, lower CAGR. The mirror ablation removes the lower state (70% always): more ETH in the ladder below EMA100, where the engine harvests ranges with staged refills on rebounds (EXP-067/068). If the refills below the EMA are where v6 earns, holding more of the asset in those rebounds should add return; the cost is deeper drawdowns in sell-offs. Completes the share-rule ablation pair.

## Change

`SHARE_BELOW_EMA = 0.7` (variant `BL`): the ladder's ETH value share is 70% in both trend states. Everything else is v6's. No new constant (70% is v6's own upper-state value).

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
| 2022 | +7.6% | +12.5% | +4.9 |
| 2023 | +32.2% | +35.8% | +3.6 |
| 2024 | +36.4% | +35.6% | -0.8 |
| 2025 | +16.3% | +17.1% | +0.9 |
| 2026-01..09-17 | +18.7% | +24.5% | +5.8 |

Wins 4/5, median +3.61 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +110.5% | 17.1% | -24.7% | 0.77 | 0.69 | $90.3k | $0.39k | 147 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +91.1% | 18.2% | -16.6% | 1.01 | 1.09 | $60.8k | $0.73k | 106 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +7.9% | 12.3% | -31.6% | 0.49 | 0.39 | $21.9k | $3.70k | 38 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | -1.7% | -2.0% | -15.2% | 0.08 | -0.13 | $11.1k | $0.04k | 18 |

Verdict: **holdout-fail** — dev passed with the widest margins of this goal (ETH CAGR 17.1% vs 14.0%, Calmar 0.69 vs 0.61, max DD −24.7% vs −22.8%, wins 4/5; WBTC CAGR 18.2% vs 17.3%, Calmar 1.09 vs 0.97, max DD −16.6% vs −17.8%). Time-split holdout: H5 ETH 2021 wins (CAGR 12.3% vs 7.0%, Calmar 0.39 vs 0.23) but H4 WBTC 2022 loses (total −1.7% vs +2.4%, max DD −15.2% vs −12.5%) → fails. Reading: holding 70% of the ladder in the asset below EMA100 adds return wherever the market rebounds (the dev windows from 2022-11 and the 2021 bull) and costs in a sustained bear (WBTC 2022), which the dev data did not hold for BTC. It is more beta in the range-harvesting state, not a better LP rule; EXP-046 (50% always) is its mirror: less beta, lower return, shallower drawdowns.

## Deviations

- Ablations chosen after EXP-052..072 (this goal's results: every rebuild-rule change moved ETH and WBTC in opposite directions; the engine ablations showed which rules carry v6's edge). Smoke test ETH 2022-05-01..06-30 (`BL,BM,BN`, inside the dev data; v6's total there, −7.9%, was seen in EXP-055's smoke test): share 70% −10.5%, the two exit ablations −7.9% with one skipped exit each. The ablations have no constant to adjust.
- The WBTC continuous segment crashed on the shared `~/.demeter` cache before any backtest ran and was rerun alone (CLAUDE.md gotcha).
