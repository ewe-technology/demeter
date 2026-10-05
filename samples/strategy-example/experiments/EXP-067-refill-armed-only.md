# EXP-067: staged refill only while the account is above its EMA (v6.54)

- Jira: QUAN-949
- Status: dropped-at-dev
- Pre-registration commit: 1fd71bb · Result commit: 9e513d2
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

In v6 an account that exited refills in four stages on a rebound from its low (+5% for three days, then +8.3 / +11.7 / +15%) whether or not the close is back above its EMA (rule 5 runs regardless of the armed flag). Below the EMA these are counter-trend buys: bear-market rallies redeploy the ladder, and the next leg down stops it out again — the F swings behind v6's chop drawdowns. Restricting the refill to armed accounts makes the engine consistent with its own trend filter. Expected: fewer bear-rally rebuilds (shallower drawdowns), the same participation once the trend turns: Calmar up, CAGR up if bear rallies were net losers for the LP. Risk: later re-entry after V-shaped bottoms.

## Change

`REFILL_ARMED_ONLY = True` (variant `BE`): rule 5 (staged refill) runs only while the account is armed (close above its EMA); the stages, the low and the confirmation are v6's. No constant.

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
| 2022 | +7.6% | -13.4% | -21.0 |
| 2023 | +32.2% | +10.6% | -21.6 |
| 2024 | +36.4% | +17.4% | -19.0 |
| 2025 | +16.3% | +12.2% | -4.1 |
| 2026-01..09-17 | +18.7% | -0.1% | -18.8 |

Wins 0/5, median -18.98 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +10.5% | 2.1% | -26.8% | 0.21 | 0.08 | $40.8k | $0.15k | 77 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +56.4% | 12.2% | -16.3% | 0.77 | 0.75 | $44.5k | $0.50k | 71 |

Verdict: **dropped-at-dev** — ETH CAGR 2.1% vs 14.0%, Calmar 0.08, max DD −26.8%, wins 0/5; WBTC CAGR 12.2% vs 17.3%, Calmar 0.75. Holdout not run. Reading: the counter-trend refill is where v6 makes its money. Refilling on the rebound from the low while still below the EMA deploys the ladder in the choppy bottoms and early recoveries where the LP earns the most per unit of IL; waiting for the EMA cuts mean F from 0.65 to 0.35 on ETH and halves the fee income (.8k vs .5k). v6 is not a trend follower with an LP attached; it is a range harvester that steps aside in trends.

## Deviations

- Sanity check before this file on Binance ETH daily closes 2020-01..2021-04 (before every window used here; F statistics only,
  no strategy run): mean F / number of F changes v6 0.883 / 35, no lower stop 0.927 / 26, refill only armed 0.834 / 30,
  full re-arm 0.751 / 14. v6's maximum drawdowns (2024 chop, 14-24 follow rebuilds) motivated the ablations (EXP-064's file).
- The WBTC continuous segment crashed on the shared `~/.demeter` cache (pickle EOFError) before any backtest ran and was rerun alone (CLAUDE.md gotcha).
