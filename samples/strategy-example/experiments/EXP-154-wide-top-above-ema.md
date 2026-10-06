# EXP-154: asymmetric ladder +40% / −20% while the close is above EMA100 (v6.140)

- Jira: QUAN-1039
- Status: fail (full-history rule; old rule: dropped-at-dev)
- Pre-registration commit: 356df3d (addendum 2253804) · Result commit: 36d7049
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

Code `59821e1` (+ `3178b15`, a no-op for this variant, see EXP-153 *Deviations*). Two verdicts, both **fail**.

### Old rule (dev + H5/H4, as pre-registered `356df3d`)

`opt:A,EO,EP` per window (tag `AEOEP`). v6 reproduces EXP-000.

| year (ETH, yearly reset) | v6 | this | gain | LP fees v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +7.2% | −0.4 | $20.1k → $19.0k |
| 2023 | +32.2% | +35.2% | +3.0 | $23.3k → $13.2k |
| 2024 | +36.4% | +27.8% | −8.6 | $30.9k → $18.4k |
| 2025 | +16.3% | +31.8% | +15.5 | $20.8k → $20.3k |
| 2026-01..09-17 | +18.7% | +18.4% | −0.3 | $6.2k → $5.9k |

Continuous: ETH CAGR 17.3% vs 14.0%, Calmar 0.70 vs 0.61, max DD −24.6% vs −22.8%; WBTC CAGR 16.5% vs 17.3%, Calmar 0.80 vs
0.97, max DD −20.7% vs −17.8%. Wins 2/5. → **dropped-at-dev** (WBTC CAGR and Calmar below v6, wins 2/5). Holdout not run.
Standalone bar (reported): passes at dev.

### Full-history rule (addendum `2253804`, Dino 2026-10-06) — the recorded verdict

| pool | v6 total / CAGR / max DD / Calmar | this | win |
|---|---|---|---|
| ETH mainnet WETH/USDC 0.05% 2021-05..2026-09 | +85.6% / 12.2% / −30.7% / 0.40 | +106.3% / 14.4% / −33.1% / 0.44 | **win** |
| ETH mainnet USDC/WETH 0.3% 2021-05..2026-09 | +94.6% / 13.2% / −26.6% / 0.50 | +102.5% / 14.1% / −29.3% / 0.48 | lose (Calmar) |
| ETH Base WETH/USDC 0.05% 2023-12..2026-09 | +53.1% / 16.5% / −31.8% / 0.52 | +71.3% / 21.2% / −32.1% / 0.66 | **win** |
| ETH Arbitrum WETH/USDC 0.05% 2023-06..2025-07 | invalid (v6 impact ledger $500k) | invalid | lose |
| ETH Base WETH/USDC 0.3% 2025-01..2026-09 | +28.1% / 15.6% / −22.0% / 0.71 | +47.6% / 25.6% / −18.9% / 1.35 | **win** |
| BTC mainnet WBTC/USDC 0.3% 2021-11..2026-09 | +54.8% / 9.4% / −25.1% / 0.37 | +49.3% / 8.6% / −25.9% / 0.33 | lose |
| BTC Base USDC/cbBTC 0.05% 2024-10..2026-09 | invalid (v6 impact ledger $58.5k) | invalid | lose |

Wins 3/7 (3/5 on the valid pools), no BTC win → **fail**.

Reading: an ETH-only improvement. On every valid ETH pool CAGR is higher (+0.9 to +10.0 pts) and on three of four the Calmar
too (mainnet 0.3% misses by 0.02); both BTC pools lose. The wider top cuts fees in strong years (ETH 2023 $13.2k vs $23.3k,
2024 $18.4k vs $30.9k: liquidity spread over +40% is thinner near the price) but keeps more ETH through rallies; on ETH that
trade pays, on WBTC (0.3% pool, fees worth more per unit of risk, FINDINGS-2026-10-05 §2) it does not — the same ETH/WBTC split
seen for recentring. A fee-tier or asset-specific version (wide top on ETH 0.05% pools only) would be a new pre-registration.

## Deviations

- v6's numbers on every window are known.
- The rule changed (Dino, 2026-10-06) after pre-registration and while the dev run was in flight; the full-history addendum
  (`2253804`) was committed before any full-history run. Both verdicts are reported; the full-history one is recorded.
- Two full-history pools are outside the model (Arbitrum `0xc696` from 2023-06-09, Base cbBTC `0xfbb6` from 2024-10-01: the
  impact ledger exceeds the equity in their thin first weeks, v6 alone $500k and $58.5k). The addendum did not define invalid
  runs; the verdict is the same either way (3/7 counted as losses, 3/5 excluded; no BTC win in both).
