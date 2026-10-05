# EXP-069: signal engine without the accounts' upper rebuild (v6.56)

- Jira: QUAN-952
- Status: dropped-at-dev
- Pre-registration commit: 7f043c5 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

The last engine rule not yet ablated is rule 4: when the close exceeds 1.2 x an account's virtual centre the centre moves up to the close (same size). Its only effect on F is through the lower stop, whose reference (0.8 x centre) then trails the rally. EXP-066 showed the stop is essential in fast crashes (ETH May 2021). Without the upper rebuild the stop stays 20% below the last refill price instead of 20% below the recent high: fewer stop-outs after rallies (less whipsaw, the chop bleed behind v6's drawdowns) but a later exit after a long rally followed by a crash. Completes the ablation set of EXP-066..068.

## Change

`NO_UPPER_REBUILD = True` (variant `BG`): rule 4 of `VirtualAccount.step` is removed (the virtual centre changes only at refill stages). Everything else is v6's. No constant.

## Pre-registration

Pre-registered together with the other experiment of the same commit (EXP-069 / EXP-070) and run in the same invocations as
`A` (v6).

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

Development (`A` and the variant in each invocation, tag `ABGBH`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +7.6% | +0.0 |
| 2023 | +32.2% | +32.2% | +0.0 |
| 2024 | +36.4% | +36.3% | -0.1 |
| 2025 | +16.3% | +16.3% | +0.0 |
| 2026-01..09-17 | +18.7% | +18.7% | +0.0 |

Wins 0/5, median +0.00 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +85.3% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.28k | 148 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |

Verdict: **dropped-at-dev** — identical to v6 to the dollar on both assets (ETH CAGR 14.0%, Calmar 0.61; WBTC 17.3%, 0.97; wins 0/5). Holdout not run. Reading: the upper rebuild only moves the reference of the lower stop; in 2022-2026 no stop-out happened after an upper rebuild, so removing it never changed F. The rule is inert on the dev data (it may matter in a long rally followed by a crash, like 2021, which this ablation cannot show without running the holdout it did not earn).

## Deviations

- Follows EXP-066..068 (completes the engine ablation set after seeing their results). Smoke test WBTC 2024-03-01..25 (`BG,BH`, no v6 run): runs.
