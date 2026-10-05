# EXP-147: fee tier: EXP-124's WBTC half, EXP-130's ETH half + rise rebuild + macro restore (v6.133)

- Jira: QUAN-1032
- Status: holdout-pass
- Pre-registration commit: f35df2e · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-139 and EXP-140 merged on the cheap pool.

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool`; below 0.3%: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`, `REBUILD_ON_RISE`, `MACRO_EVENTS = csv`, `MACRO_RESTORE`. Variant `EI`.

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
| 2022 | +7.6% | +14.1% | +6.5 |
| 2023 | +32.2% | +39.3% | +7.1 |
| 2024 | +36.4% | +39.5% | +3.2 |
| 2025 | +16.3% | +17.5% | +1.2 |
| 2026-01..09-17 | +18.7% | +18.7% | -0.0 |

Wins 4/5, median +3.17 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +117.8% | 18.0% | -24.6% | 0.88 | 0.73 | $94.3k | $0.39k | 279 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +109.6% | 21.0% | -13.8% | 1.22 | 1.52 | $64.4k | $-5.05k | 97 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +16.5% | 26.2% | -25.3% | 0.82 | 1.03 | $25.5k | $3.32k | 55 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +9.6% | 11.7% | -11.1% | 0.61 | 1.06 | $14.4k | $-0.45k | 16 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev: ETH CAGR 18.0% vs 14.0%, Calmar 0.73, max DD −24.6%, wins 4/5; WBTC = EXP-124 (21.0%, Calmar 1.52). Holdout: H5 ETH 2021 +16.5% vs +4.5% (EXP-140 without the rise rule: +16.4%); H4 WBTC 2022 +9.6% vs +2.4% (= EXP-124, rerun in the same invocation). Best H5 and best dev ETH CAGR among passes, but the rise rule adds only +0.1 pt out of time; the evidence is EXP-140's.

## Deviations

- Designed after EXP-139..143's dev results and before their holdout results were read. EXP-130's cross-asset refill (a refill stage also needs the other asset >= 1.05 x its low since the exit) is the only ETH-side rule besides v6.75 with its own out-of-time gain; it has never run on the 0.3% WBTC pool together with v6.75 (EXP-086 ran it alone and was dropped at dev, H4 never run). EXP-144 / 145 / 148 apply it to both pools as one rule; EXP-146 adds it to EXP-124's WBTC half (new on H4); EXP-147 merges EXP-139's and EXP-140's ETH halves (new on H5).
