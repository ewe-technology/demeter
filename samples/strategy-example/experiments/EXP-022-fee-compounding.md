# EXP-022: LP fees redeployed into the ladder instead of paid out (v6.17)

- Version: v6.17
- Jira: [QUAN-873](https://ewetechnology.atlassian.net/browse/QUAN-873)
- Status: dropped-at-dev
- Pre-registration commit: 54e6027 · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01: no perps, no lending). Fee compounding was tried once before
  the experiment log restarted and "discarded on purpose"; there is no record of its numbers. Dino approved
  re-testing it as a backtest only (whether the product pays rewards out is a separate decision).

## Hypothesis

v6 sells every collected fee for USDC and holds it aside (`total_quote_fee`): it is excluded from F x equity and from
every rebuild, so the ladder never grows from its own income. Over ETH 2022–26 that is $86k of fees — as much as
the whole gain — sitting idle. Most of v6's equity growth is therefore uninvested, and the book's deployed share
of equity falls over time (F x principal, not F x equity). Redeploying fees at the next build keeps the deployed
share at F x total equity. Where the ladder's own return (timing + fees − IL) is positive, compounding raises CAGR;
the drawdown scales with the larger book, so the expected cost is a deeper drawdown in proportion, not a new risk.

## Change

`FEE_COMPOUND = True` (variant `Q`): the fee reserve held aside is zero, so `follow_work`'s equity, the rebuild's
swap / band amounts and the leftover checks all use the full quote and base balances. Fees are still collected and
sold for quote exactly as in v6 (`collect_fee_as_quote`) and still reported. Nothing else changes; v6 (`A`) runs
in the same invocations. No cash yield, no perp.

## Pre-registration

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, A and Q):
  - **Arbitrum WETH/USDC 0.05%** `0xc6962004f452be9203591991d15f6b388e09e8d0` (never run in this repo; minute files
    from the team's Demeter S3 bucket, 2023-06-09..2025-07-23): continuous 2024-01-01..2025-07-23 and yearly
    segments 2024, 2025-01-01..07-23; EMA warm-up on mainnet ETH/USD;
  - **mainnet AAVE/WETH 0.3%** `0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb` (never run; 40 WETH, ETH numeraire):
    continuous 2022-01-01..2026-09-17 and yearly segments 2022..2026-09-17;
  - Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17 and Base USDC/cbBTC 0.05% continuous
    2025-01-01..2026-09-17 (v6 ran on them before, this variant never).
- Success rule (`Q` vs v6 `A`, daily equity, Calmar = CAGR / |max DD|):
  - Dev: continuous ETH and WBTC CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly
    wins ≥ 3 of 5. Else `dropped-at-dev`.
  - Holdout: on each of the four holdout pools continuous CAGR above v6's **and** Calmar ≥ v6's (if v6's CAGR is
    negative: `Q`'s CAGR above and max DD not more than 3 pts deeper) **and** max DD no more than 3 pts deeper;
    **and** yearly wins in ≥ 4 of the 7 Arbitrum + AAVE segments → `holdout-pass`, else `holdout-fail`.

## Result

Development (A and Q per invocation):

| test | v6 | this (Q) | gain | max DD v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +7.6% | 0.0 | 21.5% → 23.0% |
| 2023 | +32.2% | +34.7% | +2.5 | 13.9% → 15.7% |
| 2024 | +36.4% | +39.5% | +3.1 | 26.7% → 29.9% |
| 2025 | +16.3% | +15.9% | −0.4 | 26.9% → 30.5% |
| 2026-01..09-17 | +18.7% | +19.2% | +0.5 | 12.0% → 12.4% |

Wins 3/5, median +0.46 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees |
|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | 0.61 | $86.5k |
| ETH this | +135.4% | 19.9% | −32.5% | 0.77 | 0.61 | $132.5k |
| WBTC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.97 | $61.7k |
| WBTC this | +108.4% | 20.9% | −21.5% | 1.03 | 0.97 | |

Verdict: **dropped-at-dev** — ETH max DD 9.7 pts deeper (limit 3) and WBTC 3.7 pts deeper; Calmar unchanged on
both (0.61 / 0.97). Compounding the fees grows the ladder in proportion to equity, so return and drawdown scale
together: it is leverage on v6's own risk/return, not an improvement of it. (In yearly-reset segments the effect is
small because fees have less than a year to compound.) The holdout was not run.

## Deviations

None.
