# EXP-066: signal engine without the accounts' lower stop (v6.53)

- Jira: QUAN-948
- Status: holdout-fail
- Pre-registration commit: 1fd71bb · Result commit: 9e513d2
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

Each virtual account exits when the close falls below 0.8 x its ladder centre (rule 3), on top of the EMA exit (rule 1). v6's drawdowns are chop bleeds driven by F swinging up and down (EXP-064's analysis: 14 / 24 follow rebuilds in the ETH / WBTC max-drawdown windows); a second exit rule adds swings: an account stopped out at −20% re-enters through the staged refill a few percent higher, often while still above its EMA. If the EMA exit alone already protects against trends, removing the stop should cut whipsaw rebuilds (fewer F changes: 26 vs 35 on 2020-21 data) and their realised IL and swap cost: CAGR and Calmar up. Risk: a crash that has not yet crossed the EMA keeps the account deployed longer.

## Change

`NO_LOWER_STOP = True` (variant `BD`): rule 3 of `VirtualAccount.step` is removed; everything else (EMA exit, re-arm, upper rebuild, staged refill, the real ladder's rules) is v6's. No constant.

## Pre-registration

Pre-registered together with the other two engine ablations of the same commit (EXP-066..068) and run in the same invocations
as `A` (v6). The three are ablations of one engine and are not independent evidence of each other.

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

Development (`A` and the variant in each invocation, tag `ABDBEBF`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +7.9% | +0.3 |
| 2023 | +32.2% | +32.2% | +0.0 |
| 2024 | +36.4% | +36.3% | -0.1 |
| 2025 | +16.3% | +17.9% | +1.6 |
| 2026-01..09-17 | +18.7% | +20.6% | +1.9 |

Wins 3/5, median +0.27 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +86.9% | 14.2% | -22.4% | 0.75 | 0.63 | $88.7k | $0.24k | 143 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +90.6% | 18.1% | -17.7% | 1.05 | 1.02 | $64.8k | $0.71k | 105 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | -24.6% | -35.1% | -49.5% | -0.60 | -0.71 | $15.7k | $3.14k | 40 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +3.7% | 4.5% | -12.1% | 0.31 | 0.37 | $15.8k | $0.02k | 14 |

Verdict: **holdout-fail** — dev passed (ETH CAGR 14.2% vs 14.0%, Calmar 0.63 vs 0.61, max DD −22.4% vs −22.8%, wins 3/5; WBTC CAGR 18.1% vs 17.3%, Calmar 1.02 vs 0.97). Time-split holdout: H4 WBTC 2022 wins (CAGR 4.5% vs 2.9%, Calmar 0.37 vs 0.23) but H5 ETH 2021 collapses (total −24.6% vs +4.5%, max DD −49.5% vs −30.7%). Reading: the lower stop does nothing useful in 2022-2026 (the EMA exit fires first) and everything in a crash faster than the EMA: the May 2021 ETH crash (about −55% in two weeks) was held all the way down without it. The clearest case of this goal for the time-split holdout: dev data without such a crash cannot show what a protective rule is for. The lower stop stays.

## Deviations

- Sanity check before this file on Binance ETH daily closes 2020-01..2021-04 (before every window used here; F statistics only,
  no strategy run): mean F / number of F changes v6 0.883 / 35, no lower stop 0.927 / 26, refill only armed 0.834 / 30,
  full re-arm 0.751 / 14. v6's maximum drawdowns (2024 chop, 14-24 follow rebuilds) motivated the ablations (EXP-064's file).
- The WBTC continuous segment crashed on the shared `~/.demeter` cache (pickle EOFError) before any backtest ran and was rerun alone (CLAUDE.md gotcha).
