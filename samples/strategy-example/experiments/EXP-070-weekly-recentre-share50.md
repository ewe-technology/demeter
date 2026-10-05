# EXP-070: weekly recentre + ETH share 50% (stack of EXP-065 and EXP-046) (v6.57)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

EXP-065 (weekly time-based recentre) raised both CAGRs (ETH 17.1% vs 14.0%, WBTC 18.1% vs 17.3%) but deepened WBTC's drawdown (−22.0% vs −17.8%); EXP-046 (ETH share fixed at 50%) lowered drawdowns on every window it ran on (dev ETH −18.7%, WBTC −12.3%) at a lower CAGR. Their effects act on different things (recentre timing vs composition), so stacked they should keep part of the return gain and most of the drawdown cut: CAGR above v6 with Calmar at or above v6's on both assets. This is a stack of two tested mechanisms chosen after seeing both results, not a new idea; it is reported as such.

## Change

`WEEKLY_RECENTRE = True` and `SHARE_ABOVE_EMA = 0.5` (variant `BH`): EXP-065's Sunday full recentre and EXP-046's 50% ETH share in both trend states. Everything else is v6's. No new constant.

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

(pending)

## Deviations

- Chosen after EXP-065's and EXP-046's results (stack of two known mechanisms; selection risk stated). Smoke test WBTC 2024-03-01..25 (`BG,BH`, no v6 run): runs.
