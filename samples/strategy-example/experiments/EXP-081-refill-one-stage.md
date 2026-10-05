# EXP-081: the first refill stage deploys the account fully (v6.68)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

The staged refill below the EMA is v6's core edge (EXP-067/068). Its four stages (+5% for three days, then +8.3 / +11.7 / +15% from the low) spread the re-entry over the rebound. Collapsing them to the first confirmation tests whether the staging itself adds value or only the first signal does: fewer F changes (14 vs 35), full exposure earlier in rebounds.

## Change

`REFILL_ONE_STAGE = True` (variant `BT`): when the first refill stage confirms, the account deploys fully (stage 4). The confirmation rule, exits and upper rebuild are v6's. No constant.

## Pre-registration

Pre-registered together with the other five engine ablations of the same commit (EXP-076..081); two invocations, each with `A`
(v6): `A,BO,BP,BQ` and `A,BR,BS,BT`. The six are ablations of one engine and are not independent evidence of each other.

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

(pending)

## Deviations

- Final batch of the goal (EXP-052..081, 30 experiments): ablations of how v6's engine turns its four accounts into F, chosen after the rule ablations EXP-066..069 and EXP-073..075. Sanity check on Binance ETH closes 2020-01..2021-04 (before every window used here; F statistics only): mean F / F changes v6 0.883 / 35, one account 0.888 / 29, min 0.868 / 33, max 0.888 / 29, any 0.920 / 11, all 0.813 / 11, one-stage refill 0.916 / 14.
