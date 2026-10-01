# EXP-024: regime line = midpoint of the n-day Donchian channel instead of EMA(n) (v6.19)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

v6's exits and re-arms follow a lagging average. V6_VALIDATION shows the timing is the product (EXP-014: the F engine's timed exposure is worth about +$85k of v6's gain) and that it is sensitive to the line's speed (EMA spans ×0.8: 2022 −8.2% vs base +7.6%). The midpoint of the n-day high/low channel is a structurally different trend line (it reacts to the range edges, not to the average path) with the same lengths, so it tests whether the edge is specific to the EMA or to trend timing in general.

## Change

`REGIME = "donchian"` (variant `S`): each of the four virtual accounts (n = 90, 100, 110, 120) is armed while the daily close is above (max daily high over the last n days + min daily low over the last n days) / 2; daily high/low from the minute prices, current day included. Everything else identical to v6: exit/re-arm/stop/upper-rebuild/staged refill, F = mean of the accounts, the s rule on EMA100, ±20% valley ladder, daily 00:00 follow check.

## Pre-registration

Pre-registered together with EXP-024..027 (four regime-line variants, same four lengths 90/100/110/120 as v6's EMA spans, one constant set each, none searched) and run in the same invocations as `A`. All four results are reported.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant; only if dev passes), numbers of all three reported:
  - H1 Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` continuous 2024-01-01..2025-07-23
    (EMA warm-up on mainnet ETH/USD): v6 never ran on it with this variant; EXP-022 and EXP-023 stopped at dev;
  - H2 Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17 and H3 Base USDC/cbBTC 0.05% continuous
    2025-01-01..2026-09-17 (v6 ran on them before, this variant never).
  Honest limit: H1 and H2 share mainnet ETH's price path; the clean forward window (2026-09-18..12-31) does not exist yet.
- Success rule (variant vs v6 `A`, daily equity net of price impact, Calmar = CAGR / |max DD|):
  - Dev: continuous ETH and WBTC CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly
    wins ≥ 3 of 5. Else `dropped-at-dev`.
  - Holdout (the three deciding pools, one continuous run each): on at least 2 of the 3 pools CAGR above v6's **and**
    Calmar ≥ v6's (if v6's CAGR is negative: CAGR above and max DD not more than 3 pts deeper) **and** max DD no more
    than 3 pts deeper; **and** on the third pool Calmar ≥ v6's Calmar − 0.2 → `holdout-pass`, else `holdout-fail`.

## Result

(not run)

## Deviations

- Before this file the signal-only F series of the four regimes were generated once on ETH/USDC 2021-2026 (mean F,
  correlation with v6's F, number of F changes) to check the code runs and the signals differ; no backtest, no P&L.
