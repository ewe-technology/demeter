# EXP-054: chop gate on the EMA exit (efficiency ratio) (v6.41)

- Jira: QUAN-935
- Status: dropped-at-dev
- Pre-registration commit: 990a6ad · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino).

## Hypothesis

v6 loses −9.2% a year in the up / low-vol regime (`V6_VALIDATION.md` §5): slow grinds where the close dips under an EMA,
the account exits, then refills 5-15% higher (whipsaw). In a market that is going nowhere the LP's loss is temporary and
the fees keep coming, so an exit there only realises the whipsaw. Kaufman's efficiency ratio ER(n) = |close_t −
close_{t−n}| / Σ|Δclose| measures whether the market is trending; for a random walk its expected level is about
1/√n. Gating the EMA exit on ER ≥ 1/√n keeps accounts deployed in chop and lets them exit when the move below the EMA is
directional. This is a filter on the existing EMA exit (a market-state measure), not a new signal line: the EMA(90-120)
lines, re-arm, staged refill and the lower stop (0.8 x centre, unconditional) are unchanged. EXP-044 (two-day exit
confirmation, a time filter on the range exit) was neutral; this acts on the regime exit with market-state information.
Sources: Kaufman, *Trading Systems and Methods* (efficiency ratio); variance-ratio evidence of short-run mean reversion in
BTC (Sci. Rep. 2023, https://www.nature.com/articles/s41598-023-31618-4).

## Change

`ER_GATE = True` (variant `AQ`): an armed EMA account's exit "close < EMA(n)" fires only on days with ER(30) ≥ 1/√30
(0.1826), ER over the last 30 daily closes. On a gated day the account stays armed and deployed; the exit fires on the
first later day that still has close < EMA and ER ≥ 1/√30. Constants fixed here: 30 days, the random-walk threshold.
Everything else identical to v6.

## Pre-registration

Pre-registered together with EXP-052 and EXP-053 and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev
  windows, warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC
  0.3% 2022-01-01..2022-10-31. v6's own numbers on both are known (EXP-040..051); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly
    wins ≥ 3 of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and
    max DD no more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, `A,AO,AP,AQ`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | -6.2% | -13.8 |
| 2023 | +32.2% | +22.6% | -9.6 |
| 2024 | +36.4% | +19.9% | -16.5 |
| 2025 | +16.3% | +11.2% | -5.1 |
| 2026-01..09-17 | +18.7% | +14.9% | -3.8 |

Wins 0/5, median −9.60 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds | mean F |
|---|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 | 0.650 |
| ETH this | +35.1% | 6.6% | -27.9% | 0.41 | 0.24 | $74.6k | $0.23k | 138 | 0.685 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 | 0.672 |
| WBTC this | +81.4% | 16.6% | -19.5% | 0.90 | 0.85 | $60.4k | $0.65k | 76 | 0.753 |

Verdict: **dropped-at-dev** — wins 0/5 (median −9.6 pts), ETH CAGR 6.6% vs 14.0%, Calmar 0.24 vs 0.61, max DD 5.1 pts deeper;
WBTC also worse on all three. Holdout not run. Reading: the EMA exit is v6's protection, not its cost. A low efficiency ratio
does not mean "going nowhere": slow, noisy declines also have a low ER, and gating the exit there kept the ladder deployed
(mean F 0.685 vs 0.650) through them (2022 −6.2% vs +7.6%). The whipsaw loss in up / low-vol markets is smaller than what
the exit saves in grinding declines, and a market-state filter cannot tell the two apart on the day of the cross.

## Deviations

- A 3.5-week smoke test (ETH 2023-06-01..06-25, variants `A,AO,AP,AQ`) checked that the code runs; its numbers are not used.
