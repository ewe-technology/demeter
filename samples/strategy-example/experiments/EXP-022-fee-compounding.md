# EXP-022: LP fees redeployed into the ladder instead of paid out (v6.17)

- Version: v6.17
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
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

Pending.

## Deviations

None so far.
