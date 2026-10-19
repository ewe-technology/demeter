# EXP-181: out-of-sample check of the ETH/BTC-low BTC lock added to MGL v2, `0x4585`

- Jira: QUAN-1175 (subtask of QUAN-1107)
- Status: fail (OOS CAGR 3.4-7.6% vs v2 20.9%; ETH/BTC kept falling after the lock in 2025 Q1)
- Pre-registration commit: 50457b9 · Result commit: see registry

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

Run 2026-10-19, `v2_goal.py oos v2,rlow25,rlow25_lp,rlow25_rvol 2` (Rust engine; `result/v2_goal/oos-*`). In ETH.

| variant | IS CAGR / max DD (EXP-180) | OOS ETH x / CAGR / max DD / Calmar | beats v2 OOS | significant OOS |
|---|---|---|---|---|
| v2 | 57.33% / −26.4% | 1.384 / 20.90% / −37.2% / 0.562 | – | – |
| `rlow25` | 58.19% / −20.4% | 1.061 / 3.54% / −35.3% / 0.100 | no | no |
| `rlow25_lp` | 58.56% / −20.7% | 1.134 / 7.64% / −26.7% / 0.286 | no | no |
| `rlow25_rvol` | 58.99% / −20.4% | 1.059 / 3.41% / −35.4% / 0.096 | no | no |

ETH ratio by quarter, v2 -> `rlow25`: 2025 Q1 1.348 -> 1.117, Q2 0.969 -> 0.899, later quarters equal (0.830, 1.051,
1.180 / 1.179, 1.132 / 1.131, 0.907). ETH/BTC fell 0.0357 -> 0.0221 (−38%) in 2025 Q1: the lock swapped v2's BTC for ETH
part-way down (mean ETH share 0.47 that quarter) and gave up v2's BTC carry, the 2024 failure of EXP-180 again, larger.

Verdict: **fail** — the BTC lock loses badly out of sample (CAGR 3.4-7.6% vs 20.9%). It is a bet that ETH/BTC reverts
after a 25% fall; in-sample it was carried by the 2022 rebound, and trending ETH/BTC declines (2024, 2025 Q1) defeat it.
Max DD is shallower for `rlow25_lp` (−26.7%) only because it holds more ETH, at a cost of 13 pts of CAGR.

## Deviations

- Candidates were chosen after EXP-180's in-sample results (by construction); this OOS run is the first look at
  2025-26 for any lock variant.
