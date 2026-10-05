# EXP-063: one real sub-ladder per virtual account (v6.50)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
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

(pending)

## Deviations

- Smoke test ETH 2023-06-01..06-25 (`BA` alone, then `A,BA` after fixing a one-day late first build): totals printed (v6 −4.20%,
  this −4.20%), all four accounts changed together in that window. The one-day-late first build was a bug, fixed before this
  file; nothing else was changed after the smoke run.
