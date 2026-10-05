# EXP-067: staged refill only while the account is above its EMA (v6.54)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
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

(pending)

## Deviations

- Sanity check before this file on Binance ETH daily closes 2020-01..2021-04 (before every window used here; F statistics only,
  no strategy run): mean F / number of F changes v6 0.883 / 35, no lower stop 0.927 / 26, refill only armed 0.834 / 30,
  full re-arm 0.751 / 14. v6's maximum drawdowns (2024 chop, 14-24 follow rebuilds) motivated the ablations (EXP-064's file).
