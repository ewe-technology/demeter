# EXP-003: sleeve trailing stop whose high survives rebuilds (v6.3)

- Version: v6.3
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

EXP-002 (v6.2) put a 0.80 trailing stop on the spot sleeve but reset the stop's high at every rebuild that
re-buys the sleeve. A 20% fall also exits the ±20% ladder, whose rebuild resets the high at the fallen price, so
the stop almost never fired (3 times in the continuous ETH run, none in 2025) and max DD stayed −32.4%
(v6 −22.8%). If the high is kept across rebuilds, the stop fires once the sleeve's price is 20% below its peak,
which caps the sleeve's loss per episode near 0.5 x 20% of equity, and the drawdown should fall toward v6's.

## Change

v6.2 (`SPOT_SLEEVE = 0.5`, `SLEEVE_STOP = 0.80`) plus `SLEEVE_HIGH_KEEP = True` (v6.2: False):

- `sleeve_high` is set when the sleeve is first bought and after a re-arm; range-exit and F-follow rebuilds that
  re-buy the sleeve keep it (it still rises with every higher daily close).
- When a rebuild places no sleeve because F is 0 (and the sleeve is not stopped), the high is cleared; the next
  purchase starts a new one.
- Stop, re-arm, reserve and follow rules exactly as v6.2. No new constant.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A) and this (D) in the same invocation.
- Holdout (run once, v6 + this only): WBTC/WETH 0.05% mainnet (`0x4585fe77…`), ETH base, WBTC quote, 2 WBTC,
  yearly segments 2023, 2024, 2025, 2026-01-01..09-17 plus the continuous 2022-11-01..2026-09-17 (reported).
  EXP-001 and EXP-002 were dropped at dev, so no strategy run has touched this pool.
- Success rule (same as EXP-001/002, against v6):
  - Dev: wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, and continuous ETH max DD (daily equity) ≥ −27.8%
    (no more than 5 pts worse than v6). Otherwise `dropped-at-dev`.
  - Holdout: wins in ≥ 3 of 4 segments and median gain > 0 pts → `holdout-pass`, else `holdout-fail`.

## Result

| test | v6 | this | gain |
|---|---|---|---|

Verdict:

## Deviations

- Third trial in the spot-sleeve family, designed after seeing EXP-001/002 dev results (all dev data in-sample).
  Count it in any deflated-Sharpe or PBO assessment of this family.
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
- Smoke test before the pre-registration commit, outside every pre-registered window: ETH 2021-05-10..06-30
  (May 2021 crash, engine barely warmed up): 3 sleeve stops (refill re-arm, re-buy, stop again); this -34.3%,
  v6.2 -30.2% (unchanged from EXP-002's smoke, so the v6.2 path is intact). Design kept as written.
