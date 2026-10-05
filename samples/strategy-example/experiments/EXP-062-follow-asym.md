# EXP-062: asymmetric follow: shrink in place when F falls, v6 recentre when F rises (v6.49)

- Jira: QUAN-944
- Status: dropped-at-dev
- Pre-registration commit: c4f9b71 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

EXP-055 changed both directions of v6's follow rule at once (resize in place on F up and on F down) and lost ETH fees while
cutting drawdowns. The two directions do different things. F falls when accounts exit (close below an EMA or the lower stop):
v6 then burns the whole ladder, swaps it back to the target share and re-mints a smaller ladder around the falling price —
a recentre into weakness that realises the IL of the drop on all of the remaining liquidity. Shrinking in place only removes
the liquidity that should go and leaves the rest where it is (no swap of the remaining book). F rises on staged refills during
a rebound: there v6's recentre at today's price is what ETH rewards (EXP-023, EXP-059's extra recentres). This variant keeps
v6 on the way up and shrinks in place on the way down: it isolates the down side of EXP-055. Expected: lower swap cost and less
realised IL in sell-offs (drawdown ↓ on both assets) with v6's fee capture in recoveries (CAGR ≥ v6).

## Change

`FOLLOW_ASYM = True` (variant `AY`): on a follow event with a deployed ladder and 0 < target < current, every band's liquidity
x target/current (EXP-055's shrink; withdrawn base sold for quote); target > current, F = 0, range exits and builds from an
empty book are v6's full rebuilds. No constants.

## Pre-registration

Pre-registered together with EXP-061 (same commit) and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..060); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `AAXAY`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +3.1% | -4.5 |
| 2023 | +32.2% | +32.2% | -0.0 |
| 2024 | +36.4% | +35.6% | -0.8 |
| 2025 | +16.3% | +19.0% | +2.7 |
| 2026-01..09-17 | +18.7% | +19.7% | +0.9 |

Wins 2/5, median -0.04 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +79.6% | 13.2% | -23.0% | 0.70 | 0.58 | $83.9k | $0.26k | 146 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +85.6% | 17.3% | -17.7% | 1.01 | 0.98 | $61.9k | $0.70k | 106 |

Verdict: **dropped-at-dev** — ETH CAGR 13.2% vs 14.0%, Calmar 0.58 vs 0.61, max DD −23.0% vs −22.8%, wins 2/5; WBTC equal to v6 (CAGR 17.3%, Calmar 0.98 vs 0.97). Holdout not run. Reading: shrinking in place on F decreases (23 ETH / 17 WBTC events) neither saves WBTC anything nor protects ETH; it costs ETH fees (.9k vs .5k). With EXP-055 and EXP-061 this closes the follow-rule direction: v6's full recentre on F changes is as good as any of the four alternatives on ETH.

## Deviations

- Designed after EXP-055's result; a near-copy of EXP-055 and of EXP-061 (shared shrink step), not independent evidence.
- Smoke test (variant only): WBTC 2024-03-01..25 with `AX,AY` (no follow event, both equal).

- The ETH continuous segment crashed on the shared `~/.demeter` cache (pickle truncated) before any backtest ran and was rerun alone (CLAUDE.md gotcha); the other six segments ran as scheduled.
