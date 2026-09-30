# EXP-019: bear-phase short leg plus idle-cash yield (v6.14 + v6.4), judged on the Base USDC/WETH holdout (v6.15)

- Version: v6.15
- Jira: [QUAN-866](https://ewetechnology.atlassian.net/browse/QUAN-866)
- Status: holdout-pass
- Pre-registration commit: 6ae6426 · Result commit: d13e4cf
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

Holdout, Base USDC/WETH 0.05%, 100,000 USDC, Base Aave v3 USDC rates, run once (A, E, M, N per invocation):

| test | v6 | v6.15 (N) | gain | max DD v6 → this | v6.4 (E) | v6.14 (M) | short days |
|---|---|---|---|---|---|---|---|
| 2024 | +19.4% | +21.3% | +1.9 | 30.3% → 29.2% | +21.3% | +19.4% | 0 |
| 2025 | +13.9% | +22.6% | +8.7 | 24.4% → 24.0% | +16.2% | +20.2% | 56 |
| 2026-01..09-17 | +19.1% | +39.2% | +20.0 | 11.9% → 14.4% | +20.2% | +37.9% | 28 |

Wins 3/3, median +8.71 pts.

Continuous 2024-01-01..2026-09-17 (daily equity):

| run | total | CAGR | max DD | Sharpe | Calmar | LP fees | interest | short PnL / funding / fees |
|---|---|---|---|---|---|---|---|---|
| v6 (A) | +55.9% | 17.8% | −28.1% | 0.76 | 0.63 | $43.1k | | |
| v6.4 (E) | +63.2% | 19.8% | −27.0% | 0.83 | 0.73 | $50.4k | $7.3k | |
| v6.14 (M) | +92.4% | 27.3% | −28.1% | 0.95 | 0.97 | $46.0k | | +$31.4k / +$0.2k / −$0.7k |
| **v6.15 (N)** | **+101.4%** | **29.5%** | **−27.0%** | **1.02** | **1.09** | $53.8k | $7.7k | +$32.4k / +$0.2k / −$0.7k |

Rule: CAGR 29.5% > 17.8%, Calmar 1.09 ≥ 0.63, max DD 1.1 pts *shallower*, yearly wins 3/3 → **holdout-pass**.
v6.15 also beats v6.4 on every column (not deciding).

All pools, continuous, v6 → v6.15 (Calmar): ETH mainnet 0.61 → 1.41, Base USDC/WETH 0.63 → 1.09, WBTC mainnet
0.97 → 1.04, Base cbBTC 0.79 → 1.51; max DD shallower on all four. Sharpe: 0.73 → 1.12, 0.76 → 1.02, 1.01 → 1.00,
0.93 → 1.13.

Verdict: **holdout-pass** — the first version since v6.4 that passes a holdout, and the first to double v6's
full-history ETH result (+245.7% vs +85.4%, CAGR 30.1% vs 14.0%, max DD −21.3% vs −22.8%). Caveats: the short leg's
edge comes from bear phases (2022, 2025, 2026); in a bull-only window it is idle (2024: 0 short days), and its
losing entries are one-day crashes that revert (FTX, SVB). Base shares mainnet's ETH price path; the clean test is
the forward window (2026-09-18..12-31, January 2027). Perp counterparty / margin (min quote balance $98.9k here) and
CEX access are operational requirements v6 did not have.

## Deviations

- Registered after the dev numbers were seen (they are EXP-018's reported variant); only the Base holdout is unseen
  for this variant.
- The holdout ran once: continuous first, then the three yearly segments, one invocation each (4 workers). No reruns.
  The 2024 segment is a tie between N and E and between M and A (short never on); N's 2024 win over v6 is the cash
  yield.
