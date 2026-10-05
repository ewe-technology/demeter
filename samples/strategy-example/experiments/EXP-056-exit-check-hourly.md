# EXP-056: range-exit check every hour instead of once a day (v6.43)

- Jira: QUAN-938
- Status: dropped-at-dev
- Pre-registration commit: 29b47c1 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6 checks for a range exit once a day at 00:00 UTC. When the price leaves the ±20% ladder during the day, the ladder sits out
of range — one-sided, earning no fees — for up to 24 hours. EXP-044 tested the opposite direction (rebuild only after two daily
checks outside) and found it neutral on dev and a loser in the 2021 bull (−6.9 pts on H5): waiting costs fees in trends.
Checking every hour recentres the ladder as soon as the price has left it, so it is out of range for at most an hour: more
in-range time and fee income in trends. Risk: an exit on an intraday spike that reverts, which v6's daily check skips.
F, the ETH share and the follow rule are untouched (still once a day on the last completed day).

## Change

`EXIT_CHECK_HOURLY = True` (variant `AS`): the range-exit check (and its full rebuild) runs every hour on the hour instead of
once a day at 00:00 UTC. The rebuild itself is v6's (target share and F of the last completed day). No other change; no
constants beyond the one-hour cadence (the next coarser step of the engine's own clock, not searched).

## Pre-registration

Pre-registered together with EXP-055 (and any other file of the same commit) and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..052); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `AARASAT`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +0.4% | -7.2 |
| 2023 | +32.2% | +33.0% | +0.8 |
| 2024 | +36.4% | +23.5% | -12.8 |
| 2025 | +16.3% | +16.2% | -0.0 |
| 2026-01..09-17 | +18.7% | +18.8% | +0.1 |

Wins 2/5, median -0.05 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +67.5% | 11.6% | -23.3% | 0.62 | 0.50 | $75.5k | $0.22k | 155 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +72.6% | 15.1% | -19.9% | 0.85 | 0.76 | $50.7k | $0.72k | 110 |

Verdict: **dropped-at-dev** — ETH CAGR 11.6% vs 14.0%, Calmar 0.50 vs 0.61, max DD −23.3% vs −22.8%, wins 2/5 (2024 −12.8 pts); WBTC CAGR 15.1% vs 17.3%, Calmar 0.76 vs 0.97. Holdout not run. Reading: rebuilding within the hour of an exit catches intraday spikes that v6's daily check skips (ETH 155 rebuilds vs 147) and fee income falls (.5k vs .5k ETH, .7k vs .7k WBTC): the daily check filters noise. With EXP-044 (two-day confirmation, neutral) the exit cadence is closed: v6's once-a-day check is near the best of the three.

## Deviations

- Smoke test before this file: ETH 2022-05-01..06-30 (inside the dev data), variants `A,AR,AS`; totals printed (v6 −7.9%,
  this −8.0%, EXP-055 −6.7%). The rule has no constant to adjust.
