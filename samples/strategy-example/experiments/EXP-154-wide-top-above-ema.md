# EXP-154: asymmetric ladder +40% / −20% while the close is above EMA100 (v6.140)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: Dino, 2026-10-06: "那怎麼樣牛市可以賺的多" → two bull-only changes proposed, "好". Number EXP-154 / v6.140 and OPT
  key `EP` reserved with the goal4 session. Pre-registered together with EXP-153.

## Hypothesis

In rising markets v6's ladder keeps hitting its +20% top edge: in the up / low-vol regime of ETH 2022–26, 8 of 23 rebuilds
were top-edge exits (`decomp_daily.csv`, rebuild log), and each one turns the ladder into USDC at the edge and rebuilds it at
70% ETH, locking in the move instead of riding it. A ladder that reaches +40% above the price while the trend is up sells its
ETH more slowly as the price rises and leaves it less often, keeping more of a rally. Below EMA100 the ladder stays ±20%, so
bear-state behaviour is v6's. Related but different: EXP-013 (v6.10) shifted the whole valley 5 pts toward the trend
(+25 / −15) and was dropped at dev; this keeps the −20% lower reach and only extends the top.

## Change

Variant `EP` (`WIDE_TOP_ABOVE_EMA = 0.40`): at every build, if the last completed daily close is above EMA100 (the same test
as v6's share rule), the ladder's upper reach is +40% and its lower reach −20%; otherwise v6's ±20%. Same inverted-gaussian
shape stretched over the wider upper side; the share rule (70% / 50%) and everything else are v6's. Constant: 0.40.

## Pre-registration

Run with `A` (v6) in `opt:A,EO,EP` per window (together with EXP-153).

- Development (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): time-split out-of-time with `BINANCE_WARM=1`: H5 ETH/USDC 0.05%
  2021-05-06..12-31, H4 WBTC/USDC 0.3% 2022-01-01..10-31. Used for other variants before; this variant never ran there.
- Success rule (improvement level, `judge.py dev` / `oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.
- Reported, not deciding: bull-year gains (ETH 2023, 2024), top-edge exits, rebuild count, LP fees.

## Pre-registration addendum — full-history rule (Dino, 2026-10-06, `88f4706`)

The rule changed after this experiment was pre-registered (`356df3d`) and after its dev run had started under the old rule.
Both verdicts are reported: the old dev + H5/H4 verdict as registered above, and the full-history verdict below, which is the
one recorded as `pass` / `fail` from 2026-10-06. Written and committed before any full-history run.

- Pools (every v6-capable pool with local data, one continuous run each over all of its data, `opt:A,EO,EP` together with
  EXP-153/154, `BINANCE_WARM=1`):
  - ETH: mainnet WETH/USDC 0.05% `0x88e6` 2021-05-06..2026-09-17; mainnet USDC/WETH 0.3% `0x8ad5` 2021-05-06..2026-09-17;
    Base WETH/USDC 0.05% `0xd0b5` 2023-12-01..2026-09-17; Arbitrum WETH/USDC 0.05% `0xc696` 2023-06-09..2025-07-23; Base
    WETH/USDC 0.3% `0x6c56` 2025-01-01..2026-09-17 (2024 excluded: too thin for a $100k ladder, EXP-015).
  - BTC: mainnet WBTC/USDC 0.3% `0x99ac` 2021-11-02..2026-09-17; Base USDC/cbBTC 0.05% `0xfbb6` 2024-10-01..2026-09-17.
- Pool win: CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper (same run).
- Pass: wins on at least 4 of the 7 pools, with at least one ETH pool and one BTC pool among the wins. Otherwise fail.
  Every pool is reported.

## Result

Pending.

## Deviations

None so far. (v6's numbers on every window are known.)
