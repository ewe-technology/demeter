# EXP-153: one-sided ETH ladder above EMA100 (ETH share 100% while the close is above EMA100) (v6.139)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
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

## Result

Pending.

## Deviations

None so far. (v6's numbers on every window are known; EXP-073's share-70% result motivated the "above EMA only" design.)
