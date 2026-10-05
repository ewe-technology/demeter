# EXP-068: full deployment at the EMA re-arm instead of the staged refill (v6.55)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

The staged refill is v6's most complex rule and the main source of F changes (four stages per account, each a follow rebuild of the whole ladder: 104 of 147 ETH rebuilds are follow events). Its ablation asks whether it earns its keep against the plain trend filter it sits on: deploy an account fully when the close crosses back above its EMA, exit on the EMA or the stop, recentre at the upper rebuild. Fewer F changes (14 vs 35 on 2020-21 data) means fewer full-book swaps (the WBTC cost lever) and less whipsaw; the cost is the early re-entry the staged refill buys on rebounds below the EMA. Expected: CAGR and Calmar up on WBTC via costs; on ETH uncertain.

## Change

`REARM_FULL = True` (variant `BF`): at the re-arm (close crosses above the account's EMA) the account deploys fully (deployed 1, centre = close); rule 5 (staged refill) is off. EMA exit, lower stop and upper rebuild are v6's. No constant.

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

(pending)

## Deviations

- Sanity check before this file on Binance ETH daily closes 2020-01..2021-04 (before every window used here; F statistics only,
  no strategy run): mean F / number of F changes v6 0.883 / 35, no lower stop 0.927 / 26, refill only armed 0.834 / 30,
  full re-arm 0.751 / 14. v6's maximum drawdowns (2024 chop, 14-24 follow rebuilds) motivated the ablations (EXP-064's file).
