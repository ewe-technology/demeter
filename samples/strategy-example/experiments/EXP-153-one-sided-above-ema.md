# EXP-153: one-sided ETH ladder above EMA100 (ETH share 100% while the close is above EMA100) (v6.139)

- Jira: QUAN-1038
- Status: fail (full-history rule; old rule: dropped-at-dev)
- Pre-registration commit: 356df3d (addendum 2253804) · Result commit: see registry
- Scope: Dino, 2026-10-06: "那怎麼樣牛市可以賺的多" → two bull-only changes proposed, "好". Number EXP-153 / v6.139 and OPT
  key `EO` reserved with the goal4 session. Pre-registered together with EXP-154.

## Hypothesis

v6 lags holding in bull markets because its ETH exposure is low: ≈ 34–38% of equity in up regimes, and fees only break even
against IL in slow rises (up / low-vol 2022–26: fees +$26.4k, IL −$25.3k, delta P&L +$2.8k on 254 days;
`RESEARCH-2026-10-05-lp-vs-hold.md` §2.3). Every earlier way of adding exposure also added it in bear states and paid there:
ETH share 70% in both states (EXP-073) failed H4 (WBTC 2022 −1.7% vs +2.4%), the spot sleeve (EXP-001..003, 009) deepened
drawdowns. This change adds exposure only while the close is above EMA100; below EMA100 the share stays 50% and the EMA
exits are unchanged, so bear-state behaviour is v6's.

## Change

Variant `EO`: `SHARE_ABOVE_EMA = 1.0` (v6: 0.7); `SHARE_BELOW_EMA` stays 0.5. Structurally: v6's ±20% valley ladder holds
USDC in its bands below the price and ETH in its bands above; the ETH value share sets how the capital splits between them.
At 100% no USDC is placed, so the ladder built above EMA100 is one-sided: only the bands from the price up to +20% are funded,
all in ETH (sold progressively as the price rises through them). A fall below the build price leaves the ladder out of range
holding ETH; the existing daily range-exit check then rebuilds it as in v6 (more rebuilds are expected and are part of the
change). Everything else is v6. Constant: 1.0 (the end point of the share, not a tuned value).

## Pre-registration

Run with `A` (v6) in `opt:A,EO,EP` per window (together with EXP-154).

- Development (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): time-split out-of-time with `BINANCE_WARM=1`: H5 ETH/USDC 0.05%
  2021-05-06..12-31 (bull with the May crash), H4 WBTC/USDC 0.3% 2022-01-01..10-31 (bear). Used for other variants before;
  this variant never ran there.
- Success rule (improvement level, `judge.py dev` / `oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.
- Reported, not deciding: bull-year gains (ETH 2023, 2024 segments), rebuild count, LP fees.

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

Code `59821e1` (+ `3178b15`, see *Deviations*). Two verdicts, both **fail**.

### Old rule (dev + H5/H4, as pre-registered `356df3d`)

`opt:A,EO,EP` per window (tag `AEOEP`). v6 reproduces EXP-000 (ETH +85.4%, WBTC +85.6%).

| year (ETH, yearly reset) | v6 | this | gain | LP fees v6 → this | rebuilds v6 → this |
|---|---|---|---|---|---|
| 2022 | +7.6% | +1.7% | −5.9 | $20.1k → $20.0k | 41 → 46 |
| 2023 | +32.2% | +45.1% | +12.9 | $23.3k → $30.4k | 24 → 64 |
| 2024 | +36.4% | +34.1% | −2.3 | $30.9k → $40.6k | 29 → 76 |
| 2025 | +16.3% | +31.3% | +15.0 | $20.8k → $37.2k | 32 → 58 |
| 2026-01..09-17 | +18.7% | +20.3% | +1.6 | $6.2k → $7.2k | 24 → 32 |

Continuous: ETH CAGR 13.9% vs 14.0%, Calmar 0.55 vs 0.61, max DD −25.4% vs −22.8%; WBTC CAGR 19.8% vs 17.3%, Calmar 0.85 vs
0.97, max DD −23.3% vs −17.8% (5.5 pts deeper). Wins 3/5. → **dropped-at-dev** (ETH CAGR and Calmar below v6, WBTC max DD
beyond the 3-pt limit). Holdout not run.

### Full-history rule (addendum `2253804`, Dino 2026-10-06) — the recorded verdict

`opt:A,EO,EP`, `BINANCE_WARM=1`, one continuous run per pool from the main checkout (results in its `result/v6_validate/`).

| pool | v6 total / CAGR / max DD / Calmar | this | win |
|---|---|---|---|
| ETH mainnet WETH/USDC 0.05% 2021-05..2026-09 | +85.6% / 12.2% / −30.7% / 0.40 | +46.2% / 7.3% / −40.7% / 0.18 | lose |
| ETH mainnet USDC/WETH 0.3% 2021-05..2026-09 | +94.6% / 13.2% / −26.6% / 0.50 | +57.9% / 8.9% / −34.0% / 0.26 | lose |
| ETH Base WETH/USDC 0.05% 2023-12..2026-09 | +53.1% / 16.5% / −31.8% / 0.52 | +56.3% / 17.3% / −34.7% / 0.50 | lose |
| ETH Arbitrum WETH/USDC 0.05% 2023-06..2025-07 | invalid (v6 impact ledger $500k) | invalid | lose |
| ETH Base WETH/USDC 0.3% 2025-01..2026-09 | +28.1% / 15.6% / −22.0% / 0.71 | +40.6% / 22.1% / −22.5% / 0.98 | **win** |
| BTC mainnet WBTC/USDC 0.3% 2021-11..2026-09 | +54.8% / 9.4% / −25.1% / 0.37 | +58.6% / 9.9% / −30.0% / 0.33 | lose |
| BTC Base USDC/cbBTC 0.05% 2024-10..2026-09 | invalid (v6 impact ledger $58.5k) | invalid | lose |

Wins 1/7 (1/5 on the valid pools), no BTC win → **fail**.

Reading: the one-sided ladder does what it was built for in rallies (ETH 2023 +12.9 pts, 2025 +15.0 pts; WBTC continuous CAGR
+2.5 pts) and pays for it twice: every dip below the build price leaves the ladder out of range holding 100% ETH, so it is
rebuilt far more often (ETH 2024: 76 rebuilds vs 29) and carries full exposure into the first leg of every decline before
the EMA exit (ETH 2021–26 max DD −40.7% vs −30.7%, 2022 −5.9 pts). Fees rise (more concentrated liquidity near the price) but
not enough. Same lesson as EXP-073 / EXP-001: more ETH above the EMA is paid for in the falls that start above it.

## Deviations

- v6's numbers on every window are known; EXP-073's share-70% result motivated the "above EMA only" design.
- The rule changed (Dino, 2026-10-06) after pre-registration and while the dev run was in flight; the full-history addendum
  (`2253804`) was committed before any full-history run. Both verdicts are reported; the full-history one is recorded.
- The ETH 2025 dev segment crashed for this variant (broker assertion: a one-sided build left ~1e-30 USDC of rounding dust to
  swap with 0 USDC held). Fix `3178b15` caps every pre-placement swap at the broker's balance — a no-op for runs that did not
  raise (2025 rerun: v6 +16.2771% and EXP-154 +31.8122%, identical to the first run). The 2025 segment was rerun with
  `opt:A,EO,EP`; all full-history runs used the fixed code.
- Two full-history pools are outside the model: Arbitrum `0xc696` from 2023-06-09 and Base cbBTC `0xfbb6` from 2024-10-01
  start in their first, thin weeks and the quadratic impact ledger exceeds the equity (v6 alone: $500k and $58.5k), as
  EXP-015 found for Base 0.3% in 2024. The addendum did not define invalid runs; the verdict is the same with or without them
  (counted as losses: 1/7; excluded: 1/5).
