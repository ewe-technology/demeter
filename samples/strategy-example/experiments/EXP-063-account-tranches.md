# EXP-063: one real sub-ladder per virtual account (v6.50)

- Jira: QUAN-945
- Status: holdout-fail
- Pre-registration commit: 85e4da4 · Result commit: ffb21b1
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6's signal engine already describes four ladders: each virtual account (EMA 90 / 100 / 110 / 120) has its own deployed
fraction and its own ladder centre, with its own exits (EMA cross, lower stop at 0.8 x centre), upper rebuild (1.2 x centre)
and staged refills. The real book collapses them into one ladder: any change of any account moves F, and every F change of
≥ 12.5% burns the whole ladder, swaps all of it back to the target share and recentres all of it (104 of 147 ETH rebuilds).
Making the accounts real — four sub-ladders, each rebuilt only when its own account changes state — means (1) a change of
one account recentres and swaps only its quarter of the book (lower swap bill, the WBTC cost lever: ~14% of WBTC fee income is
paid back as rebuild swap fees), (2) the four centres drift apart in time (staggered ladders, "rebalance timing luck",
Newfound Research), so the combined liquidity is smoother and less exposed to one recentre on a bad day, and (3) each quarter
still recentres when its own account says so (upper rebuild, refill stage), keeping what ETH rewards. No new rule and no
constant: the sub-ladders follow the engine's own account logic. Expected: lower swap cost and shallower drawdowns on both
assets with a similar fee income → CAGR and Calmar up.

## Change

`ACCOUNT_TRANCHES = True` (variant `BA`). The daily frame carries each EMA account's deployed fraction and centre. Every day
at 00:00 UTC (judged on the last completed day, like v6's checks), for each account whose deployed fraction or centre changed:
its sub-ladder's own liquidity is removed (fees collected and paid out as in v6; bands shared with other sub-ladders keep the
others' liquidity), then one net swap for all rebuilt sub-ladders (pool fee and impact charged; surplus base sold so the idle
part stays quote), then each rebuilt account with deployed_j > 0 gets a v6 valley of deployed_j / 4 x book equity centred on
today's price at v6's ETH share. v6's single-ladder range exit and follow rule are switched off (each account's own upper
rebuild / lower stop / EMA exit plays that role). The first build at the window start uses the accounts' states on that day.

## Pre-registration

Pre-registered alone and run in the same invocations as `A` (v6).

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

Development (`A` and the variant in each invocation, tag `ABA`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +9.4% | +1.8 |
| 2023 | +32.2% | +18.9% | -13.3 |
| 2024 | +36.4% | +26.4% | -10.0 |
| 2025 | +16.3% | +18.3% | +2.0 |
| 2026-01..09-17 | +18.7% | +21.3% | +2.6 |

Wins 3/5, median +1.81 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +89.7% | 14.6% | -23.7% | 0.75 | 0.62 | $89.4k | $0.31k | 167 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +87.5% | 17.6% | -17.6% | 1.01 | 1.00 | $63.3k | $0.73k | 120 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | -7.2% | -10.8% | -35.4% | -0.04 | -0.30 | $18.5k | $6.26k | 46 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +2.9% | 3.4% | -11.4% | 0.26 | 0.30 | $14.4k | $0.04k | 20 |

Verdict: **holdout-fail** — dev passed the improvement rule (ETH CAGR 14.6% vs 14.0%, Calmar 0.62 vs 0.61, max DD −23.7% vs −22.8%, wins 3/5; WBTC CAGR 17.6% vs 17.3%, Calmar 1.00 vs 0.97, max DD −17.6% vs −17.8%; fee income up on both, .4k vs .5k and .3k vs .7k). Time-split holdout: H4 WBTC 2022 wins (CAGR 3.4% vs 2.9%, Calmar 0.30 vs 0.23, max DD −11.4% vs −12.5%) but H5 ETH 2021 loses badly (total −7.2% vs +4.5%, max DD −35.4% vs −30.7%) → fails. Reading: the dev gain came from higher fee income, not from the lower swap bill the hypothesis predicted (swap notional rose slightly: ETH .59M vs .52M). In the 2021 ETH bull the four accounts changed state far more often (126 sub-ladder rebuilds in eight months), on a pool that was thinner then (price impact .3k vs .7k), and the September 2021 drop (−12.7% vs −7.6% that month) hit staggered sub-ladders built higher. Staggering the centres did not survive a regime the dev data did not hold.

## Deviations

- Smoke test ETH 2023-06-01..06-25 (`BA` alone, then `A,BA` after fixing a one-day late first build): totals printed (v6 −4.20%,
  this −4.20%), all four accounts changed together in that window. The one-day-late first build was a bug, fixed before this
  file; nothing else was changed after the smoke run.
