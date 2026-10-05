# EXP-064: CPPI floor on the strategy's own net value (v6.51)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6's maximum drawdowns are not crashes: on ETH (−22.8%, 2024-03-11..09-06) and WBTC (−17.8%, 2024-04-08..10-23) they build up
over six months of chop in which the engine's F swings up and down (14 and 24 follow rebuilds in those windows; WBTC's price
even ended higher). The engine reads only price; it does not know the book is bleeding. Constant-proportion portfolio
insurance (Black & Perold 1992; drawdown control, Grossman & Zhou 1993) scales exposure by the cushion above a floor on the
strategy's own value: m = (W/HWM − floor) / (1 − floor). Using v6's own lower stop (0.8) as the floor, the ladder is halved at
a 10% drawdown of the book and emptied at 20%, then refilled as the book recovers. Expected: drawdowns capped near 20% and the
chop bleed cut (Calmar ↑); CAGR ↑ only if the cut periods were net losers — the main risk is a slower recovery with less capital
deployed (counter-evidence: CTA practice reports CPPI costs return in V-shaped recoveries).

## Change

`CPPI_FLOOR = 0.8` (variant `BB`): at the daily 00:00 follow check the target becomes F x m, m = clip((W / HWM − 0.8) / 0.2, 0, 1),
W = total book value (ladder + wallet, paid-out fees included), HWM = the highest W seen at the daily checks since the start.
Everything else (follow threshold, rebuilds, share) is v6's. The floor is v6's LOWER_STOP, not a new constant.

## Pre-registration

Pre-registered together with EXP-065 (same commit) and run in the same invocations as `A` (v6).

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

- The drawdown windows of v6 named in the hypothesis were measured on v6's own dev runs (baseline, already known) before this
  file. Smoke test WBTC 2024-03-01..25 (`BB,BC`, no v6 run): runs, m fell to 0.54.
