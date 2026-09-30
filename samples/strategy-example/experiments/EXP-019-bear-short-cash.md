# EXP-019: bear-phase short leg plus idle-cash yield (v6.14 + v6.4), judged on the Base USDC/WETH holdout (v6.15)

- Version: v6.15
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Parents: `EXP-004-idle-cash-yield.md` (v6.4, holdout-pass), `EXP-018-bear-short-leg.md` (v6.14, dev pass,
  holdout-fail on WBTC). Same code: variant `N` of EXP-018 (commit 39d04ac).

## Hypothesis

The two mechanisms act on different states of the book and do not interact: the short leg is on only while F = 0
and the trend is down (EXP-018), the cash yield works on the idle USDC share (1 − F) at all times (EXP-004). v6.14
failed its WBTC holdout because its losing short episodes are short-lived entries right after one-day crashes (FTX
2022-11-10, SVB 2023-03-10, SEC suit 2023-06-06: −2.8, −4.0, −2.9% on 0.5x), which shrink the book just before
the 2023–24 LP years; the lost compounding cost ≈ 5 pts of total and Calmar 0.91 vs 0.97. The cash yield adds
≈ +1.5 pts a year on the same book (EXP-004), which more than offsets it. In EXP-018 the combination (`N`, reported
there, not deciding) beat v6 on all three pools: ETH Calmar 1.41 vs 0.61, WBTC 1.04 vs 0.97, Base cbBTC 1.51 vs
0.79. This experiment registers the combination as its own version and judges it on a pool no short-leg run has
touched.

Two literature fixes for the short-lived losing entries were screened on Binance closes before this file and
rejected (they cut the winning episodes more than the losing ones): a 3-day entry confirmation (v6's
`REFILL_CONFIRM_DAYS` mirrored; BTC leg 2020–26 +11.9% → +9.4%) and the "Momentum Turning Points" Bear-state rule
(Garg, Goulding, Harvey, Mazzoleni, JFE 2023: short only if the 1-month return is also negative; ETH leg +45.8% →
+24.7%, BTC +11.9% → +8.9%). Neither is registered.

## Change

Variant `N` exactly as in EXP-018: `BEAR_SHORT = 0.5`, `BEAR_SHORT_LOOKBACK = 365`, perp mechanics of EXP-014,
funding from Binance ETHUSDT, plus EXP-004's `CASH_APR = "pool"` (Base Aave v3 USDC rates on the Base pool). v6
(`A`), v6.4 (`E`) and v6.14 (`M`) in the same invocations.

## Pre-registration

- Development (already seen, EXP-018, variant `N`): ETH continuous +245.7% / CAGR 30.1% / max DD −21.3% / Sharpe
  1.12 / Calmar 1.41 vs v6 +85.4% / 14.0% / −22.8% / 0.73 / 0.61; WBTC Calmar 1.04 vs 0.97; Base cbBTC 1.51 vs 0.79.
- Holdout (run once, A, E, M, N): **Base USDC/WETH 0.05%** (`0xd0b53d9277642d899df5c87a3966a349a798f224`),
  100,000 USDC, EMA warm-up on mainnet ETH/USD (as EXP-004), yearly segments 2024, 2025, 2026-01-01..09-17 and the
  continuous 2024-01-01..2026-09-17 run. No run with a short leg has touched this pool. Not virgin data: v6 and
  v6.4 ran on it (EXP-004, EXP-015, EXP-017), and its ETH price path is the mainnet one already seen in dev (Base
  2024–26 is inside the mainnet dev window) — what is new is the pool's own fees, liquidity and Base Aave rates.
- Forward holdout (clean): ETH and BTC 2026-09-18..2026-12-31 in January 2027, same rule.
- Success rule on the Base holdout, `N` vs v6 (`A`):
  - continuous CAGR above v6's, **and**
  - continuous Calmar (CAGR / |max DD|, daily equity) ≥ v6's, **and**
  - continuous max DD no more than 3 pts deeper than v6's, **and**
  - yearly return wins in ≥ 2 of 3 segments
  → `holdout-pass`, else `holdout-fail`. `N` vs v6.4 (`E`) reported, not deciding.

## Result

Pending.

## Deviations

- Registered after the dev numbers were seen (they are EXP-018's reported variant); only the Base holdout is unseen
  for this variant.
