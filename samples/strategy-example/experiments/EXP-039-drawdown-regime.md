# EXP-039: regime = close within 20% of its n-day high, n = 90/100/110/120 (v6.30)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

A drawdown filter asks a different question from a moving average: how far is the price from its recent peak. 20% is the ladder's own half-width and v6's lower-stop distance, so the exit rule matches the unit the LP already uses: when the price is 20% under its n-day high the ladder is already beyond its lower edge. Re-arm is automatic when the high rolls out of the window or the price recovers.

## Change

`REGIME = "dd"`, `DD_FRAC = 0.20` (variant `AF`): accounts n = 90, 100, 110, 120 armed while the daily close is above 0.8 × the highest daily close of the last n days. Everything else identical to v6.

## Pre-registration

Pre-registered together with EXP-036..039 (four regime lines of different structure, one constant set each, none searched) and run in the same invocations as `A`. Both success levels are judged from the same runs; all four results are reported.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant; only if dev passes), numbers of all three reported:
  - H1 Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` continuous 2024-01-01..2025-07-23
    (EMA warm-up on mainnet ETH/USD): v6 never ran on it with this variant;
  - H2 Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17 and H3 Base USDC/cbBTC 0.05% continuous
    2025-01-01..2026-09-17 (v6 ran on them before, this variant never).
  Honest limit: H1 and H2 share mainnet ETH's price path; the clean forward window (2026-09-18..12-31) does not exist yet.
- Success rules (variant vs v6 `A`, daily equity net of price impact, Calmar = CAGR / |max DD|; two levels, README *Success levels*; the same runs decide both):
  - Improvement: dev: continuous ETH and WBTC CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper, ETH yearly wins ≥ 3 of 5.
    Holdout (three pools): on at least 2 of 3 CAGR above v6's **and** Calmar ≥ v6's (if v6's CAGR is negative: CAGR above and max DD
    not more than 3 pts deeper) **and** max DD no more than 3 pts deeper, **and** on the third pool Calmar ≥ v6's − 0.2 → `holdout-pass`.
  - Standalone: dev: continuous ETH and WBTC Calmar ≥ 0.60 and max DD no deeper than −30%, ETH positive in ≥ 4 of 5 yearly segments.
    Holdout: total return > 0 on all three pools, Calmar ≥ 0.50 on at least 2 of 3, max DD no deeper than −35% on all three → `holdout-pass` (standalone).
  - Dev failing both levels → `dropped-at-dev`; the holdout is run (once) when dev passes at least one level, and each level is judged on it separately.

## Result

(not run)

## Deviations

- The code was smoke-tested on a three-week window (2023-06-01..06-20) and the signal-only F series checked once on ETH/USDC (mean F, correlation with v6's F, number of F changes); no P&L evidence. A first KAMA variant (slow constant = n) was dropped before pre-registration because its signal was degenerate (mean F 0.32): it was replaced by the drawdown-from-high regime (EXP-039). The candidates were chosen after seeing batches 1-3: lines faster than the EMA(90-120) lost, range-structure lines (Donchian) won on ETH only, so this batch tries slower and structurally different lines.
