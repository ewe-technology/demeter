# EXP-145: v6.75 + cross-asset refill + routing + rise rebuild (one rule for both pools) (v6.131)

- Jira: QUAN-1030
- Status: dropped-at-dev
- Pre-registration commit: f35df2e · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-144 with the rise rebuild (EXP-137): stages that pass both filters are deployed the day they fire.

## Change

Variant `EG`: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`, `SWAP_ROUTE = pool`, `REBUILD_ON_RISE` on every pool.

## Pre-registration

Pre-registered together with EXP-144..148 (same commit), run with `A` (v6) in `A,EF,EG,EH,EI,EJ` per window.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..081) and both windows have been used for other variants; this
  variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `AEFEGEHEIEJ`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +15.0% | +7.4 |
| 2023 | +32.2% | +38.9% | +6.7 |
| 2024 | +36.4% | +38.3% | +1.9 |
| 2025 | +16.3% | +17.4% | +1.1 |
| 2026-01..09-17 | +18.7% | +18.6% | -0.1 |

Wins 4/5, median +1.94 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +115.9% | 17.8% | -24.5% | 0.88 | 0.73 | $95.9k | $0.37k | 149 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +84.1% | 17.0% | -17.0% | 0.97 | 1.00 | $54.7k | $-4.66k | 103 |

Verdict: **dropped-at-dev** — ETH CAGR 17.8%, Calmar 0.73, wins 4/5; WBTC 17.0% < v6 17.3%. Same WBTC failure as EXP-144. Holdout not run.

## Deviations

- Designed after EXP-139..143's dev results and before their holdout results were read. EXP-130's cross-asset refill (a refill stage also needs the other asset >= 1.05 x its low since the exit) is the only ETH-side rule besides v6.75 with its own out-of-time gain; it has never run on the 0.3% WBTC pool together with v6.75 (EXP-086 ran it alone and was dropped at dev, H4 never run). EXP-144 / 145 / 148 apply it to both pools as one rule; EXP-146 adds it to EXP-124's WBTC half (new on H4); EXP-147 merges EXP-139's and EXP-140's ETH halves (new on H5).
