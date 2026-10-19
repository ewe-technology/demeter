# EXP-181: out-of-sample check of the ETH/BTC-low BTC lock added to MGL v2, `0x4585`

- Jira: QUAN-1175 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

EXP-180 found an added layer that cuts v2's in-sample max drawdown in ETH by 6 pts and raises CAGR: hold v2's BTC share
as ETH once ETH/BTC is 25% under its 90-day high, until ETH/BTC is back above its EMA50 (`rlow25`), best stacked with the
EXP-179 `rvol` filter. It missed EXP-180's significant bar in-sample (CAGR +1.66 < +2 pts), so EXP-180 gave it no OOS run.
If the lock is a real effect, it also cuts the out-of-sample drawdown and keeps CAGR at or above v2.

## Change

No new code: variants `rlow25`, `rlow25_lp`, `rlow25_rvol` in `experiments/v2_goal.py` exactly as run in EXP-180 (v2
untouched, added layers only). These are the three EXP-180 layers that beat v2 in-sample on the EXP-178 / 179 bar
(`rlow25_e100` is identical to `rlow25` in-sample and is not run).

## Pre-registration

- Segment: OOS 2025-01-01..2026-09-17 only (IS numbers are EXP-180's); v2 rerun in the same batch; net value in ETH incl.
  rewards.
- Verdicts per variant, both reported: **beats v2** (CAGR above, Calmar >=, max DD no more than 3 pts deeper) and
  **significant** (CAGR >= v2 + 2 pts, max DD >= 3 pts shallower, Calmar >=).
- Pass = at least one variant beats v2 out-of-sample with max DD shallower than v2. "Significant on both halves" is
  not reachable here (none was significant IS) and is not claimed.
- Run once; no variant is added after the OOS numbers are seen.

## Result

(pending)

## Deviations

- Candidates were chosen after EXP-180's in-sample results (by construction); this OOS run is the first look at
  2025-26 for any lock variant.
